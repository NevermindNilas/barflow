// barflow/_core.cpp — C++ core for the BarFlow progress bar library.
//
// Hot path design: `advance()` / `Tracker.tp_iternext` is a single atomic
// fetch_add into a counter on the `Task` struct. A background render
// thread wakes on a condition variable timeout (adaptive frame interval)
// and snapshots the atomic, runs the column pipeline, and writes to
// stderr via WriteConsoleW on Windows (UTF-16 transcoded) or write(2)
// elsewhere.
//
// Phase 1 surface added to the POC:
//   - Multi-task: `add_task(total, desc)` → task id, rendered as a stack
//     of bars with ANSI cursor-up between frames.
//   - Column system: Python passes a list of column tuples of the form
//     (type:int, text:str, width:int, frames:list[str]|None, color:str).
//     Nine built-in column types handled entirely in C++.
//   - `write_above(text)` primitive: acquires the render mutex, walks
//     back to the top of the bar area, clears to end-of-screen, emits the
//     user text, and notifies the render thread to repaint. Lets Python
//     stdout/stderr proxies interleave prints with live bars.
//   - POSIX build path: ANSI native, `write(2)` to fd 2, TIOCGWINSZ width.
//
// The hot path (`tick`, `advance`, `Tracker.tp_iternext`) is unchanged
// from the POC and remains a single `fetch_add` plus the CPython call
// trampoline. No column or task-lookup work happens on the producer side.

#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <algorithm>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <system_error>
#include <thread>
#include <utility>
#include <vector>

#ifdef _WIN32
#  define WIN32_LEAN_AND_MEAN
#  define NOMINMAX
#  include <windows.h>
#  include <io.h>
#else
#  include <errno.h>
#  include <sys/ioctl.h>
#  include <unistd.h>
#endif

// Portable branch hints. Prefer C++20 [[likely]]/[[unlikely]] attributes
// on compilers that support them, fall back to __builtin_expect elsewhere.
// These are macros that wrap a boolean condition — usable inside `if (...)`.
#if defined(__GNUC__) || defined(__clang__)
#  define BARFLOW_LIKELY(x)   (__builtin_expect(!!(x), 1))
#  define BARFLOW_UNLIKELY(x) (__builtin_expect(!!(x), 0))
#else
#  define BARFLOW_LIKELY(x)   (x)
#  define BARFLOW_UNLIKELY(x) (x)
#endif

namespace {

enum ColumnType : int {
    COL_TEXT        = 0,
    COL_DESCRIPTION = 1,
    COL_BAR         = 2,
    COL_PERCENT     = 3,
    COL_COUNT       = 4,
    COL_RATE        = 5,
    COL_ELAPSED     = 6,
    COL_ETA         = 7,
    COL_SPINNER     = 8,
    COL_CALLBACK    = 9,
};

// Move-only PyObject* owner. Columns hold user-supplied callables for
// COL_CALLBACK; without this, vector moves during parse_columns would
// double-decref. The destructor acquires the GIL so it's safe to drop
// from any thread (e.g. render thread tear-down).
struct PyObjectRef {
    PyObject* p{nullptr};

    PyObjectRef() = default;
    PyObjectRef(const PyObjectRef&) = delete;
    PyObjectRef& operator=(const PyObjectRef&) = delete;
    PyObjectRef(PyObjectRef&& o) noexcept : p(o.p) { o.p = nullptr; }
    PyObjectRef& operator=(PyObjectRef&& o) noexcept {
        if (this != &o) { reset(); p = o.p; o.p = nullptr; }
        return *this;
    }
    ~PyObjectRef() { reset(); }

    void reset() {
        if (p) {
            PyGILState_STATE s = PyGILState_Ensure();
            Py_DECREF(p);
            PyGILState_Release(s);
            p = nullptr;
        }
    }
    void assign_new_ref(PyObject* o) {
        // Takes ownership of a new reference.
        reset();
        p = o;
    }
};

struct Column {
    int         type{COL_TEXT};
    std::string text;                      // literal text / format hint
    int         width{40};                 // bar width
    std::vector<std::string> frames;       // precomputed spinner frames
    std::string color;                     // ANSI color seq (e.g. "\x1b[36m")

    // Python callable for COL_CALLBACK. Called once per rendered frame
    // with a types.SimpleNamespace task snapshot; return value (str) is
    // appended to the frame buffer. Held under PyObjectRef so vector
    // moves remain correct without manual INCREF/DECREF bookkeeping.
    PyObjectRef py_callable;

    // Flex bar stretches its body to fill whatever screen cells remain
    // after every other column has been measured. Only meaningful for
    // COL_BAR. `width` holds a fallback used when terminal width can't
    // be queried (e.g. output redirected to a file).
    bool flex{false};

    // Bar glyph set — only meaningful when type == COL_BAR.
    // Left empty for non-bar columns. Defaults are filled in by
    // install_default_columns() or parse_columns() when missing.
    std::string fill;          // "█" by default
    std::string empty_ch;      // " " by default  (`empty` is reserved on STL-adjacent headers)
    std::vector<std::string> partials;  // 7 partials 1/8..7/8 by default
    std::string left_border;   // "|" by default
    std::string right_border;  // "|" by default

    // Precomputed row strings used by render_column(COL_BAR): `fill`
    // repeated `width` times and `empty_ch` repeated `width` times.
    // Populated by finalize_bar_cache() once width/glyphs are known,
    // then the render path can append a prefix of these via a single
    // memcpy instead of running a per-cell loop. `fill_byte_len` and
    // `empty_byte_len` are the byte length of a single glyph so the
    // render path can compute the slice length without another lookup.
    std::string filled_full;
    std::string empty_full;
    size_t      fill_byte_len{0};
    size_t      empty_byte_len{0};
};

// Precompute the full-width filled/empty bar rows from `fill`/`empty_ch`
// so render_column can copy slices of them instead of append-looping
// across `width` cells. Call this once width and glyphs are known.
inline void finalize_bar_cache(Column& c) {
    if (c.type != COL_BAR) return;
    int w = c.width > 0 ? c.width : 40;
    c.fill_byte_len  = c.fill.size();
    c.empty_byte_len = c.empty_ch.size();
    c.filled_full.clear();
    c.empty_full.clear();
    c.filled_full.reserve(c.fill_byte_len  * static_cast<size_t>(w));
    c.empty_full.reserve (c.empty_byte_len * static_cast<size_t>(w));
    for (int i = 0; i < w; ++i) c.filled_full.append(c.fill);
    for (int i = 0; i < w; ++i) c.empty_full.append(c.empty_ch);
}

namespace default_glyphs {
    // Smooth Unicode-block bar: ▏▎▍▌▋▊▉█
    inline void apply(Column& c) {
        if (c.fill.empty())         c.fill = "\xe2\x96\x88";        // █
        if (c.empty_ch.empty())     c.empty_ch = " ";
        if (c.partials.empty()) {
            c.partials = {
                "\xe2\x96\x8f", // ▏ 1/8
                "\xe2\x96\x8e", // ▎ 2/8
                "\xe2\x96\x8d", // ▍ 3/8
                "\xe2\x96\x8c", // ▌ 4/8
                "\xe2\x96\x8b", // ▋ 5/8
                "\xe2\x96\x8a", // ▊ 6/8
                "\xe2\x96\x89", // ▉ 7/8
            };
        }
        if (c.left_border.empty())  c.left_border = "|";
        if (c.right_border.empty()) c.right_border = "|";
    }
}

// Cacheline size assumed to be 64B. We deliberately don't use
// std::hardware_destructive_interference_size because it's ABI-fragile
// on libstdc++ and pessimistically 128 on Apple silicon.
static constexpr size_t kCacheLine = 64;

struct Task {
    // --- Producer-written hot cacheline ---
    // `completed` is the only field touched on the hot path
    // (tick/advance/iternext). It gets its own 64B line.
    alignas(kCacheLine) std::atomic<uint64_t> completed{0};
    // Pad out the rest of the cacheline so consumer writes to the
    // fields below never invalidate the producer's line. sizeof(atomic)
    // is typically 8 on x86_64, so we pad by 56 bytes.
    char _pad_after_completed[kCacheLine - sizeof(std::atomic<uint64_t>)]{};

    // --- Consumer-only cacheline ---
    // Written only by the render thread (under render_mtx) after init.
    // Aligned to its own 64B block to avoid false sharing with `completed`.
    alignas(kCacheLine) uint64_t    total{0};
    uint64_t    start_time_ns{0};
    std::string description;
    uint64_t    last_snapshot{0};
    int         id{0};
    bool        visible{true};
};

struct ProgressState {
    // tasks/columns mutation requires render_mtx. Reads from the render
    // thread or non-hot-path producers also take render_mtx. The hot path
    // (tick/advance/Tracker_iternext) does NOT touch tasks — it goes
    // through `task0` (a stable Task*) and the per-Task atomic counter,
    // so it remains lock-free under the free-threaded build.
    std::vector<std::unique_ptr<Task>> tasks;
    std::vector<Column>                 columns;

    // Cached column-pipeline flags. Filled once after parse_columns /
    // install_default_columns (single-threaded init); read by the render
    // thread on every wakeup to avoid re-scanning `columns` on each tick.
    // `flex_bar_idx` is the column index of the first flex bar (-1 if
    // none) — render_frame uses it directly instead of re-scanning.
    bool has_spinner_col{false};
    bool has_callback_col{false};
    int  flex_bar_idx{-1};

    // Stable pointer to task[0] for the lock-free hot path. Set on first
    // task creation, never reassigned. Task lives in unique_ptr on the
    // heap so the pointer is stable across vector reallocations.
    std::atomic<Task*>      task0{nullptr};

    std::mutex              render_mtx;
    std::condition_variable render_cv;
    std::atomic<bool>       running{false};
    std::thread             render_thread;
    std::once_flag          close_once;

    double min_interval{0.05};
    bool   disable{false};
    bool   vt_enabled{false};
    bool   is_console{false};
    bool   closed{false};

    int      last_rendered_lines{0};
    uint64_t frame_tick{0};

    // Cell count of each visible task's rendered content in the
    // previous frame. Used on the next frame to compute how many
    // physical rows the terminal actually consumed *at the current
    // width*, so a live resize (which re-wraps already-written lines)
    // can be cleaned up before painting the new frame. Cleared by
    // write_above and on close.
    std::vector<int> last_task_cells;

    std::string scratch;   // reusable per-frame render buffer
    // Per-column staging strings reused across frames; sized to
    // columns.size() lazily in render_frame. Used by both the flex path
    // and the delta-render (diff) path.
    std::vector<std::string> col_out_cache;

    // --- Delta-render (diff-based frame output) cache ---
    // Previous-frame per-(task, column) rendered bytes and their visible
    // cell widths. A column whose new output matches byte-for-byte AND
    // whose preceding columns on the same line all kept their cell
    // widths identical can be skipped by emitting a cursor-right escape
    // (\x1b[<n>C) instead of its bytes. The diff path is engaged only
    // when every task line has at least one such skippable column, so
    // for tiny frames (changed bytes dominated by escape overhead) we
    // fall through to the full-emit path unchanged.
    //
    // Shape: prev_col_out[task_index][column_index] — rebuilt whenever
    // task or column count changes, or whenever write_above invalidates
    // the cursor position. `delta_valid` gates the whole thing: when
    // false, the next render_frame does a full emit and primes the
    // cache.  `prev_visible_mask[ti]` stores per-column visibility of
    // the previous frame (flex-path column dropping). When the visible
    // set shifts for a task, positions shift and the cache for that
    // task is invalidated (the line is fully re-emitted).
    std::vector<std::vector<std::string>> prev_col_out;
    std::vector<std::vector<int>>         prev_col_cells;
    std::vector<std::vector<uint8_t>>     prev_visible_mask;
    bool                                   delta_valid{false};
    int                                    prev_term_w{-1};
#ifdef _WIN32
    std::wstring wscratch; // reusable per-frame UTF-16 transcode buffer
#endif

#ifdef _WIN32
    HANDLE console_handle{nullptr};
#else
    int    fd{2};
#endif
};

inline uint64_t now_ns() {
    return static_cast<uint64_t>(
        std::chrono::steady_clock::now().time_since_epoch().count());
}

// -------- Console init / write primitives --------

void init_console(ProgressState* st) {
#ifdef _WIN32
    st->console_handle = GetStdHandle(STD_ERROR_HANDLE);
    if (st->console_handle == INVALID_HANDLE_VALUE || st->console_handle == nullptr) {
        st->is_console = false;
        return;
    }
    DWORD mode = 0;
    if (GetConsoleMode(st->console_handle, &mode)) {
        st->is_console = true;
        // NB: we deliberately do NOT set DISABLE_NEWLINE_AUTO_RETURN.
        // With that flag, a lone LF only moves the cursor down and
        // leaves the column unchanged — which breaks multi-task
        // stacked bars because task2's content starts at the column
        // where task1 left off instead of at column 0. Keeping
        // auto-CR on LF makes `\n` mean "next line, col 0" like every
        // other POSIX-shaped terminal.
        DWORD want = mode | ENABLE_VIRTUAL_TERMINAL_PROCESSING;
        if (SetConsoleMode(st->console_handle, want)) {
            st->vt_enabled = true;
        }
    }
#else
    st->fd = 2;
    st->is_console = isatty(st->fd) != 0;
    st->vt_enabled = st->is_console;
#endif
}

void write_bytes(ProgressState* st, const char* data, size_t len) {
    if (st->disable || len == 0) return;
#ifdef _WIN32
    if (st->is_console && st->console_handle) {
        int wlen = MultiByteToWideChar(CP_UTF8, 0, data,
                                       static_cast<int>(len),
                                       nullptr, 0);
        if (wlen > 0) {
            // Reusable transcode buffer. resize() never shrinks capacity,
            // so after the first frame this is an O(1) length update.
            st->wscratch.resize(static_cast<size_t>(wlen));
            MultiByteToWideChar(CP_UTF8, 0, data, static_cast<int>(len),
                                st->wscratch.data(), wlen);
            DWORD written = 0;
            const wchar_t* p = st->wscratch.data();
            DWORD remaining = static_cast<DWORD>(wlen);
            while (remaining > 0) {
                DWORD chunk = remaining > 32768 ? 32768 : remaining;
                if (!WriteConsoleW(st->console_handle, p, chunk, &written, nullptr)) break;
                p += written;
                remaining -= written;
            }
            return;
        }
    }
    fwrite(data, 1, len, stderr);
    fflush(stderr);
#else
    // Handle short writes and EINTR. write(2) is allowed to return
    // fewer bytes than requested (e.g. on pipes with full buffers) or
    // -1/EINTR if interrupted by a signal.
    const char*  p         = data;
    size_t       remaining = len;
    while (remaining > 0) {
        ssize_t wrote = write(st->fd, p, remaining);
        if (wrote < 0) {
            if (errno == EINTR) continue;
            break;  // EPIPE / EBADF / ... give up silently.
        }
        if (wrote == 0) break;  // shouldn't happen on a regular fd.
        p         += wrote;
        remaining -= static_cast<size_t>(wrote);
    }
#endif
}

// -------- Formatters --------

// Write decimal digits of `v` into `buf` (which must have room for 20 bytes
// — the longest uint64_t is 20 digits). Returns number of bytes written.
// MSVC's snprintf is locale-aware and noticeably slower than a hand-rolled
// itoa for the hot column-rendering path, so we open-code the conversion.
inline size_t u64_to_chars(char* buf, uint64_t v) {
    char  tmp[20];
    size_t n = 0;
    do {
        tmp[n++] = static_cast<char>('0' + (v % 10));
        v /= 10;
    } while (v != 0);
    // tmp holds digits least-significant-first — reverse into buf.
    for (size_t i = 0; i < n; ++i) buf[i] = tmp[n - 1 - i];
    return n;
}

// Append two decimal digits zero-padded (for MM:SS style formatting).
inline void append_two_digit(std::string& out, uint64_t v) {
    if (v > 99) v = 99;
    char c[2] = {
        static_cast<char>('0' + (v / 10)),
        static_cast<char>('0' + (v % 10)),
    };
    out.append(c, 2);
}

void format_number(std::string& out, uint64_t v) {
    char tmp[20];
    size_t n = u64_to_chars(tmp, v);
    out.append(tmp, n);
}

void format_rate(std::string& out, double rate) {
    char tmp[32];
    int n;
    // Keep snprintf for the %.2f / %.1f formatting — hand-rolling a locale-
    // independent double formatter would dwarf the savings from integer
    // conversion, and rate isn't on the per-iteration hot path anyway.
    if (rate >= 1e6)      n = std::snprintf(tmp, sizeof(tmp), "%.2fM", rate / 1e6);
    else if (rate >= 1e3) n = std::snprintf(tmp, sizeof(tmp), "%.2fk", rate / 1e3);
    else                  n = std::snprintf(tmp, sizeof(tmp), "%.1f",  rate);
    out.append(tmp, static_cast<size_t>(n));
}

void format_seconds(std::string& out, double s) {
    if (s < 0 || s != s) s = 0;
    uint64_t total = static_cast<uint64_t>(s);
    uint64_t h = total / 3600;
    uint64_t m = (total / 60) % 60;
    uint64_t sec = total % 60;
    if (h > 0) {
        char tmp[20];
        size_t n = u64_to_chars(tmp, h);
        out.append(tmp, n);
        out.push_back(':');
        append_two_digit(out, m);
        out.push_back(':');
        append_two_digit(out, sec);
    } else {
        append_two_digit(out, m);
        out.push_back(':');
        append_two_digit(out, sec);
    }
}

// -------- Column rendering --------

// Cached `types.SimpleNamespace` constructor. Populated lazily on first
// CallbackColumn render so cold-import of `barflow` does not pay the
// `import types` cost (~0.3 ms on Linux) for users who never construct
// a CallbackColumn. `g_empty_tuple` stays eager — PyTuple_New(0) is free.
static PyObject* g_simple_namespace = nullptr;  // lazy; see ensure_simple_namespace
static PyObject* g_empty_tuple      = nullptr;

// Resolve `types.SimpleNamespace` on first use. Caller MUST hold the GIL.
// Returns true on success and leaves `g_simple_namespace` populated; on
// failure returns false with the Python exception cleared (callers fall
// back to nullptr snapshots, same as the GIL-acquire-failure path).
static bool ensure_simple_namespace() {
    if (g_simple_namespace) return true;
    PyObject* types_mod = PyImport_ImportModule("types");
    if (!types_mod) { PyErr_Clear(); return false; }
    PyObject* sn = PyObject_GetAttrString(types_mod, "SimpleNamespace");
    Py_DECREF(types_mod);
    if (!sn) { PyErr_Clear(); return false; }
    g_simple_namespace = sn;  // strong ref held for module lifetime
    return true;
}

struct RenderCtx {
    bool      vt_enabled;
    double    elapsed;
    double    rate;
    double    frac;      // completed / total, clamped [0,1]; -1 if unknown
    uint64_t  frame_tick;
    // Built once per task per frame when callback columns are present,
    // then shared across every COL_CALLBACK in that frame. nullptr when
    // no callback columns exist, or when GIL acquisition failed.
    PyObject* snapshot;
    // Flex bar width override. -1 = ignore, use col.width. >=0 = use
    // this body width for flex bars (computed after measuring non-bar
    // columns against the terminal width).
    int       bar_width_override;
};

// Truncate a rendered byte string to at most `max_cells` display cells
// and append an ANSI reset so any dangling style from the cut-off tail
// cannot bleed into whatever is rendered after it. ANSI CSI sequences
// pass through atomically (never split mid-escape). Used by the flex
// path when even the leftmost visible column is wider than the
// terminal — rather than wrap, we hard-clip.
static void truncate_to_cells(std::string& s, int max_cells) {
    if (max_cells < 0) max_cells = 0;
    int cells = 0;
    size_t i = 0;
    size_t last_safe = 0;
    const size_t n = s.size();
    while (i < n) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        if (c == 0x1b && i + 1 < n && s[i + 1] == '[') {
            size_t j = i + 2;
            while (j < n) {
                unsigned char x = static_cast<unsigned char>(s[j++]);
                if (x >= 0x40 && x <= 0x7E) break;
            }
            i = j;
            last_safe = i;
            continue;
        }
        if (c == '\r' || c == '\n' || c == '\t') {
            ++i; last_safe = i; continue;
        }
        int step;
        if      ((c & 0x80) == 0)    step = 1;
        else if ((c & 0xE0) == 0xC0) step = 2;
        else if ((c & 0xF0) == 0xE0) step = 3;
        else if ((c & 0xF8) == 0xF0) step = 4;
        else                          step = 1;
        if (cells >= max_cells) break;
        ++cells;
        i += step;
        last_safe = i;
    }
    s.resize(last_safe);
    s.append("\x1b[0m", 4);
}

// Count visible cells in a rendered byte string. Skips ANSI CSI escape
// sequences (\x1b[...<final>) and counts UTF-8 code points as single
// cells. Accurate for ASCII + box-drawing/block glyphs barflow renders;
// slightly off for wide CJK/emoji (each would count as 1 cell instead
// of 2), but good enough to size the flex bar and still leave margin.
static int count_display_cells(const char* data, size_t n) {
    int cells = 0;
    size_t i = 0;
    while (i < n) {
        unsigned char c = static_cast<unsigned char>(data[i]);
        if (c == 0x1b && i + 1 < n && data[i + 1] == '[') {
            i += 2;
            while (i < n) {
                unsigned char x = static_cast<unsigned char>(data[i++]);
                if (x >= 0x40 && x <= 0x7E) break;
            }
            continue;
        }
        if (c == '\r' || c == '\n' || c == '\t') { ++i; continue; }
        if ((c & 0x80) == 0)      { i += 1; ++cells; }
        else if ((c & 0xE0) == 0xC0) { i += 2; ++cells; }
        else if ((c & 0xF0) == 0xE0) { i += 3; ++cells; }
        else if ((c & 0xF8) == 0xF0) { i += 4; ++cells; }
        else                         { i += 1; }
    }
    return cells;
}

static inline int count_display_cells(const std::string& s) {
    return count_display_cells(s.data(), s.size());
}

// Terminal width in columns, or 0 if it cannot be determined (output
// piped / redirected / not a TTY). Queried each frame so resize events
// are picked up automatically. `BARFLOW_TERM_WIDTH` env var pins a
// value (for tests and for users who want a fixed bar regardless of
// the real terminal size).
static int query_terminal_width(ProgressState* st) {
    const char* env = std::getenv("BARFLOW_TERM_WIDTH");
    if (env && *env) {
        int v = std::atoi(env);
        if (v > 0) return v;
    }
#ifdef _WIN32
    if (st->console_handle && st->is_console) {
        CONSOLE_SCREEN_BUFFER_INFO csbi;
        if (GetConsoleScreenBufferInfo(st->console_handle, &csbi)) {
            int w = csbi.srWindow.Right - csbi.srWindow.Left + 1;
            return w > 0 ? w : 0;
        }
    }
    return 0;
#else
    struct winsize ws;
    if (ioctl(st->fd, TIOCGWINSZ, &ws) == 0 && ws.ws_col > 0) {
        return static_cast<int>(ws.ws_col);
    }
    return 0;
#endif
}

void render_column(const Column& col, const Task& t,
                   std::string& buf, const RenderCtx& ctx) {
    // Apply style/color to every column uniformly. The style field is a
    // preformatted SGR escape like "\x1b[1;38;2;255;136;0m" produced by
    // barflow.style.style(). Empty → no wrapping. The reset is emitted
    // after the column body below.
    const bool wrap_style = !col.color.empty() && ctx.vt_enabled;
    if (wrap_style) buf.append(col.color);

    switch (col.type) {
    case COL_TEXT:
        buf.append(col.text);
        break;

    case COL_DESCRIPTION:
        buf.append(t.description);
        break;

    case COL_BAR: {
        buf.append(col.left_border);
        int bar_w;
        if (col.flex && ctx.bar_width_override >= 0) {
            bar_w = ctx.bar_width_override;
        } else {
            bar_w = col.width > 0 ? col.width : 40;
        }
        // Fast path: use the precomputed filled_full/empty_full slices
        // when the cache is populated. Flex bars bypass the cache since
        // their width is chosen per frame and the cache was sized for
        // the fallback width.
        const bool have_cache =
            !col.flex &&
            !col.filled_full.empty() && !col.empty_full.empty() &&
            col.fill_byte_len  > 0   && col.empty_byte_len  > 0;
        if (ctx.frac >= 0.0) {
            double filled_eighths = ctx.frac * static_cast<double>(bar_w) * 8.0;
            int full = static_cast<int>(filled_eighths) / 8;
            int partial = static_cast<int>(filled_eighths) % 8;  // 0..7
            if (full > bar_w) full = bar_w;
            if (have_cache) {
                // Copy `full` filled cells as a single memcpy slice.
                buf.append(col.filled_full.data(),
                           static_cast<size_t>(full) * col.fill_byte_len);
            } else {
                for (int i = 0; i < full && i < bar_w; ++i) buf.append(col.fill);
            }
            if (full < bar_w) {
                if (partial > 0 && !col.partials.empty()) {
                    // Map 1..7 (partial level) onto 0..N-1 (partials index).
                    size_t idx = static_cast<size_t>(partial - 1)
                                 * col.partials.size() / 7;
                    if (idx >= col.partials.size()) idx = col.partials.size() - 1;
                    buf.append(col.partials[idx]);
                } else if (partial >= 4) {
                    // No partials defined → round.
                    buf.append(col.fill);
                } else {
                    buf.append(col.empty_ch);
                }
                int remaining_empty = bar_w - full - 1;
                if (remaining_empty > 0) {
                    if (have_cache) {
                        buf.append(col.empty_full.data(),
                                   static_cast<size_t>(remaining_empty)
                                       * col.empty_byte_len);
                    } else {
                        for (int i = 0; i < remaining_empty; ++i) buf.append(col.empty_ch);
                    }
                }
            }
        } else {
            // Unknown total: a single filled cell bounces across the width.
            int pos = static_cast<int>(ctx.frame_tick % (bar_w * 2));
            if (pos >= bar_w) pos = (bar_w * 2) - 1 - pos;
            if (have_cache) {
                // Left run of empties, single fill cell, right run of empties.
                buf.append(col.empty_full.data(),
                           static_cast<size_t>(pos) * col.empty_byte_len);
                buf.append(col.fill);
                int right = bar_w - pos - 1;
                if (right > 0) {
                    buf.append(col.empty_full.data(),
                               static_cast<size_t>(right) * col.empty_byte_len);
                }
            } else {
                for (int i = 0; i < bar_w; ++i) {
                    buf.append(i == pos ? col.fill : col.empty_ch);
                }
            }
        }
        buf.append(col.right_border);
        break;
    }

    case COL_PERCENT: {
        if (ctx.frac >= 0.0) {
            int pct = static_cast<int>(ctx.frac * 100.0);
            if (pct < 0)   pct = 0;
            if (pct > 100) pct = 100;
            // Right-aligned in a 3-char field: "  0%" .. "100%".
            char tmp[4];
            if (pct >= 100) {
                tmp[0] = '1'; tmp[1] = '0'; tmp[2] = '0';
            } else if (pct >= 10) {
                tmp[0] = ' ';
                tmp[1] = static_cast<char>('0' + pct / 10);
                tmp[2] = static_cast<char>('0' + pct % 10);
            } else {
                tmp[0] = ' ';
                tmp[1] = ' ';
                tmp[2] = static_cast<char>('0' + pct);
            }
            tmp[3] = '%';
            buf.append(tmp, 4);
        } else {
            buf.append("  ?%", 4);
        }
        break;
    }

    case COL_COUNT:
        format_number(buf, t.last_snapshot);
        if (t.total > 0) {
            buf.push_back('/');
            format_number(buf, t.total);
        }
        break;

    case COL_RATE:
        format_rate(buf, ctx.rate);
        buf.append(" it/s", 5);
        break;

    case COL_ELAPSED:
        format_seconds(buf, ctx.elapsed);
        break;

    case COL_ETA: {
        double remaining = 0.0;
        if (ctx.rate > 0 && t.total > 0 && t.last_snapshot < t.total) {
            remaining = static_cast<double>(t.total - t.last_snapshot) / ctx.rate;
        }
        format_seconds(buf, remaining);
        break;
    }

    case COL_SPINNER: {
        if (!col.frames.empty()) {
            buf.append(col.frames[ctx.frame_tick % col.frames.size()]);
        }
        break;
    }

    case COL_CALLBACK: {
        // GIL must already be held by the caller (render_frame batches
        // the acquire across all callback columns in a frame). snapshot
        // is nullptr only when GIL acquisition failed — bail silently.
        if (!col.py_callable.p || !ctx.snapshot) break;
        PyObject* res = PyObject_CallOneArg(col.py_callable.p, ctx.snapshot);
        if (res) {
            if (PyUnicode_Check(res)) {
                Py_ssize_t rlen = 0;
                const char* rs = PyUnicode_AsUTF8AndSize(res, &rlen);
                if (rs) {
                    // Strip embedded \r and \n — a stray newline from
                    // a user callback would drop the cursor to the
                    // next row mid-frame, desyncing the per-task cell
                    // accounting and leaving zombies on resize. Rare
                    // in practice but trivially defensible here.
                    for (Py_ssize_t k = 0; k < rlen; ++k) {
                        char ch = rs[k];
                        if (ch == '\r' || ch == '\n') continue;
                        buf.push_back(ch);
                    }
                }
            }
            Py_DECREF(res);
        } else {
            // Print traceback to stderr and continue — a bad callback
            // must not bring down the render thread.
            PyErr_WriteUnraisable(col.py_callable.p);
        }
        break;
    }
    }

    if (wrap_style) buf.append("\x1b[0m", 4);
}

// Build a `types.SimpleNamespace` snapshot for the given task. Caller
// must hold the GIL. Returns a new reference, or nullptr on failure
// (exception is cleared — we don't want to surface it from the render
// thread).
static PyObject* build_task_snapshot(const Task& t, const RenderCtx& ctx) {
    if (!ensure_simple_namespace() || !g_empty_tuple) return nullptr;

    PyObject* kw = PyDict_New();
    if (!kw) { PyErr_Clear(); return nullptr; }

    auto set_u64 = [&](const char* k, uint64_t v) {
        PyObject* o = PyLong_FromUnsignedLongLong(v);
        if (o) { PyDict_SetItemString(kw, k, o); Py_DECREF(o); }
    };
    auto set_f64 = [&](const char* k, double v) {
        PyObject* o = PyFloat_FromDouble(v);
        if (o) { PyDict_SetItemString(kw, k, o); Py_DECREF(o); }
    };
    auto set_str = [&](const char* k, const std::string& v) {
        PyObject* o = PyUnicode_FromStringAndSize(v.data(),
                                                  static_cast<Py_ssize_t>(v.size()));
        if (o) { PyDict_SetItemString(kw, k, o); Py_DECREF(o); }
    };

    set_u64("completed",  t.last_snapshot);
    set_u64("total",      t.total);
    set_f64("elapsed",    ctx.elapsed);
    set_f64("rate",       ctx.rate);
    set_f64("speed",      ctx.rate);          // rich-compat alias
    set_f64("percentage", ctx.frac >= 0.0 ? ctx.frac * 100.0 : -1.0);
    set_f64("fraction",   ctx.frac);
    set_u64("frame_tick", ctx.frame_tick);
    set_u64("task_id",    static_cast<uint64_t>(t.id));
    set_str("description", t.description);

    PyObject* snap = PyObject_Call(g_simple_namespace, g_empty_tuple, kw);
    Py_DECREF(kw);
    if (!snap) { PyErr_Clear(); return nullptr; }
    return snap;
}

// Fallback column set when user passes no columns.
// Compute cached column-pipeline flags from `st->columns`. Call once
// after column setup (single-threaded init) so the render thread can
// read them on every wakeup without re-scanning the column list.
static void refresh_column_flags(ProgressState* st) {
    bool spinner = false, callback = false;
    int  flex_idx = -1;
    for (size_t ci = 0; ci < st->columns.size(); ++ci) {
        const auto& c = st->columns[ci];
        if (c.type == COL_SPINNER)  spinner = true;
        if (c.type == COL_CALLBACK) callback = true;
        if (c.type == COL_BAR && c.flex && flex_idx < 0) {
            flex_idx = static_cast<int>(ci);
        }
    }
    st->has_spinner_col  = spinner;
    st->has_callback_col = callback;
    st->flex_bar_idx     = flex_idx;
}

void install_default_columns(ProgressState* st) {
    st->columns.clear();
    auto mk = [&](int type, std::string text = "", int width = 0,
                  std::vector<std::string> frames = {},
                  std::string color = "") {
        Column c;
        c.type = type;
        c.text = std::move(text);
        c.width = width;
        c.frames = std::move(frames);
        c.color = std::move(color);
        if (c.type == COL_BAR) {
            default_glyphs::apply(c);
            finalize_bar_cache(c);
        }
        st->columns.push_back(std::move(c));
    };
    mk(COL_DESCRIPTION);
    mk(COL_TEXT, ": ");
    mk(COL_PERCENT);
    mk(COL_TEXT, " ");
    mk(COL_BAR, "", 40, {}, "\x1b[36m");
    mk(COL_TEXT, " ");
    mk(COL_COUNT);
    mk(COL_TEXT, " [");
    mk(COL_ELAPSED);
    mk(COL_TEXT, "<");
    mk(COL_ETA);
    mk(COL_TEXT, ", ");
    mk(COL_RATE);
    mk(COL_TEXT, "]");
}

// -------- Frame / render loop --------

// Append an ANSI cursor-right (CUF) escape `\x1b[<n>C` to `buf`. No-op
// when n <= 0. Used by the delta-render path to skip over unchanged
// column spans instead of re-emitting their bytes.
static inline void append_cursor_right(std::string& buf, int n) {
    if (n <= 0) return;
    buf.append("\x1b[", 2);
    char tmp[20];
    size_t len = u64_to_chars(tmp, static_cast<uint64_t>(n));
    buf.append(tmp, len);
    buf.push_back('C');
}

// Minimum bytes-saved threshold below which we just re-emit the
// column's bytes instead of a cursor-right escape. A CUF escape is
// 4-6 bytes (\x1b[N..C); emitting it for a column whose output is
// only 3 bytes actively costs us bandwidth. 6 bytes is a safe floor
// — we only skip when we are confident it is a net win.
static constexpr int kDeltaMinSkipCells = 6;

void render_frame(ProgressState* st) {
    if (st->tasks.empty() || st->columns.empty()) return;

    std::string& buf = st->scratch;
    buf.clear();

    // Pull cached column-pipeline flags (computed once at column setup).
    // `has_callback` controls GIL acquisition; `flex_bar_idx` selects the
    // two-stage flex render path; `has_spinner_col` is reserved for the
    // dirty-skip heuristic that lives in render_loop.
    const bool has_callback = st->has_callback_col;
    const int  flex_bar_idx = st->flex_bar_idx;
    PyGILState_STATE gil_state{};
    if (has_callback) {
        gil_state = PyGILState_Ensure();
    }

    // Terminal width is queried for BOTH paths now — the non-flex path
    // still needs it to compute how many physical rows the previous
    // frame currently occupies (the terminal re-wraps already-written
    // content on resize, so a task that printed 1 row at 120 columns
    // may now span 3 rows at 40). 0 means "unknown" (pipe/redirect) —
    // we fall back to the old "1 row per task" assumption.
    int term_w = query_terminal_width(st);

    // Decide delta-render eligibility *before* the walk-back. Delta emit
    // relies on the previous frame's bytes still being on screen (CUF
    // escapes skip over unchanged columns), so when it is going to run
    // we must NOT erase the old rows — just reposition the cursor. If
    // delta is off we still erase every row up front. Resize, task count
    // change, or column count change forces a full redraw.
    const size_t ntasks = st->tasks.size();
    const size_t ncols = st->columns.size();
    bool use_delta = st->delta_valid && st->vt_enabled;
    if (use_delta) {
        if (st->prev_col_out.size()      != ntasks ||
            st->prev_col_cells.size()    != ntasks ||
            st->prev_visible_mask.size() != ntasks ||
            st->prev_term_w              != term_w) {
            use_delta = false;
        }
        if (use_delta) {
            for (size_t ti = 0; ti < ntasks; ++ti) {
                if (st->prev_col_out[ti].size()      != ncols ||
                    st->prev_col_cells[ti].size()    != ncols ||
                    st->prev_visible_mask[ti].size() != ncols) {
                    use_delta = false;
                    break;
                }
            }
        }
    }

    // Walk the cursor back to the top of the previous bar area. On the
    // non-delta path we *also* erase every physical row it used to
    // occupy; on the delta path we leave the old bytes in place so the
    // CUF skips downstream land on the right characters. Physical rows
    // are computed against the *current* terminal width because
    // terminals soft-wrap already-written content on resize — a task
    // that printed one line at 120 cols now spans three rows at 40.
    //
    // Per-row \x1b[2K beats \x1b[J for erasing: Erase-in-Display's
    // semantics vary with the scrollback / buffer state (the bar
    // area commonly straddles the last visible row) and in practice
    // leaves the top of the old bar area behind on Windows Terminal
    // after a resize. \x1b[1B / \x1b[1A move between rows without
    // ever emitting \n, which avoids a scroll if the bar area is
    // sitting against the bottom edge of the viewport.
    if (!st->last_task_cells.empty() && st->vt_enabled) {
        int total_rows = 0;
        for (int c : st->last_task_cells) {
            int r;
            if (term_w > 0) {
                r = (c + term_w - 1) / term_w;
                if (r < 1) r = 1;
            } else {
                r = 1;
            }
            total_rows += r;
        }
        // Overshoot by one — cheap insurance against an off-by-one in
        // cells_per_task (e.g. a callback column emitted a glyph the
        // terminal treats as 2 cells but we counted as 1).
        int clear_rows = total_rows + 1;
        int rows_up    = total_rows > 0 ? total_rows - 1 : 0;

        if (rows_up > 0) {
            buf.append("\x1b[", 2);
            char tmp[20];
            size_t n = u64_to_chars(tmp, static_cast<uint64_t>(rows_up));
            buf.append(tmp, n);
            buf.push_back('A');
        }
        buf.push_back('\r');

        if (!use_delta) {
            for (int i = 0; i < clear_rows; ++i) {
                buf.append("\x1b[2K", 4);       // erase entire current row
                if (i < clear_rows - 1) {
                    buf.append("\x1b[1B", 4);   // down one row, no scroll
                }
            }
            // Walk back to the top of the now-empty bar area.
            if (clear_rows > 1) {
                buf.append("\x1b[", 2);
                char tmp[20];
                size_t n = u64_to_chars(
                    tmp, static_cast<uint64_t>(clear_rows - 1));
                buf.append(tmp, n);
                buf.push_back('A');
            }
            buf.push_back('\r');
        }
    } else {
        buf.push_back('\r');
    }

    // Previous frame's per-task cells are no longer needed; reuse the
    // vector in place as we render this frame.
    st->last_task_cells.clear();

    // Per-column output staging. Reused across tasks and frames so the
    // allocator sees the same size-class after a few frames. With the
    // delta-render path, we now *always* stage into col_out[] (even on
    // the non-flex path) so we can diff against the previous frame on
    // a per-column basis before emitting.
    std::vector<std::string>& col_out = st->col_out_cache;
    if (col_out.size() != ncols) {
        col_out.assign(ncols, std::string{});
    }

    // Ensure the delta cache storage is sized correctly for this
    // frame's task/column shape. Even when use_delta is false we still
    // want to prime it after rendering so the NEXT frame can diff.
    if (st->prev_col_out.size()   != ntasks) st->prev_col_out.resize(ntasks);
    if (st->prev_col_cells.size() != ntasks) st->prev_col_cells.resize(ntasks);
    if (st->prev_visible_mask.size() != ntasks) st->prev_visible_mask.resize(ntasks);
    for (size_t ti = 0; ti < ntasks; ++ti) {
        if (st->prev_col_out[ti].size()      != ncols) st->prev_col_out[ti].assign(ncols, std::string{});
        if (st->prev_col_cells[ti].size()    != ncols) st->prev_col_cells[ti].assign(ncols, 0);
        if (st->prev_visible_mask[ti].size() != ncols) st->prev_visible_mask[ti].assign(ncols, 0);
    }

    int visible = 0;
    uint64_t tns = now_ns();
    size_t task_index_in_state = SIZE_MAX;
    for (auto& task : st->tasks) {
        ++task_index_in_state;  // wraps from SIZE_MAX to 0 on first iteration
        if (!task->visible) continue;
        if (visible > 0) buf.append("\r\n", 2);
        // When use_delta is false the walk-back already erased every
        // row up front — no per-task erase needed. When use_delta is
        // true we intentionally left the old bytes on screen for the
        // delta path; any task that falls back to full-emit erases its
        // own row inline below before re-emitting.
        if (!use_delta && st->vt_enabled) buf.append("\x1b[2K", 4);
        // Mark the offset where this task's visible content begins so
        // we can measure its display-cell footprint after rendering.
        size_t task_start_offset = buf.size();

        uint64_t completed = task->completed.load(std::memory_order_acquire);
        task->last_snapshot = completed;

        RenderCtx ctx;
        ctx.vt_enabled = st->vt_enabled;
        ctx.elapsed = static_cast<double>(tns - task->start_time_ns) / 1e9;
        ctx.rate = ctx.elapsed > 0 ? static_cast<double>(completed) / ctx.elapsed : 0.0;
        ctx.frac = task->total > 0
            ? std::min(1.0, static_cast<double>(completed) / static_cast<double>(task->total))
            : -1.0;
        ctx.frame_tick = st->frame_tick;
        ctx.snapshot = has_callback ? build_task_snapshot(*task, ctx) : nullptr;
        ctx.bar_width_override = -1;

        // Visibility mask for this task's columns in THIS frame. The
        // flex path may zero entries; the non-flex path leaves them all
        // 1. We track it so the diff comparison against prev_visible_mask
        // can detect flex-collapse transitions and invalidate the cache
        // for the affected line.
        std::vector<char> visible_cols(ncols, 1);

        // Per-column display-cell counts for THIS frame, populated inline
        // as each column is rendered. The flex path measures non-bar
        // columns up front (it needs the widths to plan the collapse),
        // then patches in the flex bar's width post-render. The non-flex
        // path measures lazily after each render_column. Either way the
        // delta-emit path downstream reads `this_cells` directly without
        // re-walking col_out.
        std::vector<int> this_cells(ncols, 0);

        if (flex_bar_idx < 0) {
            // Non-flex: render every column into its col_out[] slot and
            // measure its cell width in the same pass. On frames where
            // everything changed, the downstream emit-loop just appends
            // col_out[ci] straight into buf — net cost is one extra
            // string copy which is cheap compared to WriteConsoleW.
            for (size_t ci = 0; ci < ncols; ++ci) {
                col_out[ci].clear();
                render_column(st->columns[ci], *task, col_out[ci], ctx);
                this_cells[ci] = count_display_cells(col_out[ci]);
            }
        } else {
            // Flex path — progressive collapse so that a resize into a
            // narrow window never wraps the line:
            //   1. Shrink the bar body down to `body_min` cells.
            //   2. If that still doesn't fit, hide the bar entirely
            //      (body + borders).
            //   3. If still too wide, drop UI columns right-to-left.
            //   4. If the leftmost visible column is on its own still
            //      wider than the terminal, hard-truncate it.
            const int N = static_cast<int>(st->columns.size());

            // Measure every non-bar column. The flex bar is rendered
            // later once body_w is known; its cell width is patched into
            // `this_cells` post-render below.
            int sum_non_bar = 0;
            for (int ci = 0; ci < N; ++ci) {
                col_out[ci].clear();
                if (ci == flex_bar_idx) continue;
                render_column(st->columns[ci], *task, col_out[ci], ctx);
                this_cells[ci] = count_display_cells(col_out[ci]);
                sum_non_bar += this_cells[ci];
            }

            // Plan: decide body_w and which columns stay visible.
            int body_w = st->columns[flex_bar_idx].width > 0
                         ? st->columns[flex_bar_idx].width : 40;
            bool hide_bar = false;
            const int border_cells = 2;  // left + right bar borders
            const int body_min     = 5;  // smallest "useful" bar body

            if (term_w > 0) {
                const int safety = 1;
                int budget_for_bar = term_w - sum_non_bar - safety;
                if (budget_for_bar >= border_cells + body_min) {
                    body_w = budget_for_bar - border_cells;
                    if (body_w > 400) body_w = 400;
                } else {
                    // Step 2: hide the bar.
                    hide_bar = true;
                    visible_cols[flex_bar_idx] = 0;

                    // The leftmost non-bar column with content is the
                    // "anchor" — typically the task description. We
                    // never drop it outright; if it alone exceeds the
                    // terminal width, we truncate it instead.
                    int anchor = -1;
                    for (int ci = 0; ci < N; ++ci) {
                        if (ci != flex_bar_idx && this_cells[ci] > 0) {
                            anchor = ci;
                            break;
                        }
                    }

                    // Step 3: drop from the right while still over.
                    // Budget drops the safety margin here — once we
                    // are shedding content, we want every cell we can
                    // salvage.
                    int available = term_w;
                    int cum = sum_non_bar;
                    for (int ci = N - 1; ci > anchor && cum > available; --ci) {
                        if (ci == flex_bar_idx) continue;
                        if (this_cells[ci] == 0) { visible_cols[ci] = 0; continue; }
                        cum -= this_cells[ci];
                        visible_cols[ci] = 0;
                    }

                    // Step 4: even the anchor alone may be too wide.
                    // Hard-clip it — the alternative is wrapping the
                    // line, which breaks the cursor-up reset and
                    // corrupts subsequent frames.
                    if (cum > available && anchor >= 0) {
                        int others = 0;
                        for (int ci = 0; ci < N; ++ci) {
                            if (!visible_cols[ci] || ci == anchor) continue;
                            others += this_cells[ci];
                        }
                        int budget = available - others;
                        if (budget < 0) budget = 0;
                        truncate_to_cells(col_out[anchor], budget);
                        // truncate_to_cells mutated col_out[anchor]; refresh
                        // its cell count so downstream delta-diff reads the
                        // post-clip width.
                        this_cells[anchor] = count_display_cells(col_out[anchor]);
                    }
                }
            }

            // Render the flex bar if it survived the collapse, then
            // patch its cell width into the per-column table.
            if (!hide_bar) {
                ctx.bar_width_override = body_w;
                render_column(st->columns[flex_bar_idx], *task,
                              col_out[flex_bar_idx], ctx);
                ctx.bar_width_override = -1;
                this_cells[flex_bar_idx] = count_display_cells(col_out[flex_bar_idx]);
            }
        }

        // --- Delta emit ---
        //
        // Decide, for this task's line, whether to delta-emit or
        // full-emit. Delta-emit walks columns left-to-right; each
        // unchanged column whose cell width is >= kDeltaMinSkipCells
        // becomes a `\x1b[<n>C` cursor-right escape. Any changed
        // column is emitted in full, flushing any pending skip run
        // first so the cursor is aligned before the bytes land.
        //
        // Precondition for skipping column `ci`: every column j < ci
        // on this task's line must also be either skipped OR have its
        // cell width unchanged from the previous frame — otherwise
        // the absolute column position where `ci` lands shifts
        // between frames and the cached bytes would appear in the
        // wrong place on screen. We track this with `positions_stable`
        // which flips false on the first column whose cell width
        // changed.
        //
        // Also: per-task visibility must match the previous frame.
        // If a column was visible last frame but is hidden now (or
        // vice-versa), every column after the transition shifts, so
        // we fall back to full-emit for this task's line.
        size_t ti = task_index_in_state;
        auto&  prev_out    = st->prev_col_out[ti];
        auto&  prev_cells  = st->prev_col_cells[ti];
        auto&  prev_vis    = st->prev_visible_mask[ti];

        // `this_cells[]` was filled inline as each column was rendered
        // above (non-flex path) or measured against the flex collapse
        // plan + flex bar (flex path) — no need to re-walk col_out here.

        // Check if the visibility mask changed for this task.
        bool task_delta_ok = use_delta;
        if (task_delta_ok) {
            for (size_t ci = 0; ci < ncols; ++ci) {
                if (static_cast<uint8_t>(visible_cols[ci]) != prev_vis[ci]) {
                    task_delta_ok = false;
                    break;
                }
            }
        }

        if (task_delta_ok) {
            bool positions_stable = true;
            int  pending_skip     = 0;  // accumulated cells to skip
            for (size_t ci = 0; ci < ncols; ++ci) {
                if (!visible_cols[ci]) continue;
                const Column& col = st->columns[ci];
                bool always_dirty = (col.type == COL_SPINNER);
                bool bytes_match  = (!always_dirty) &&
                                    positions_stable &&
                                    col_out[ci] == prev_out[ci];
                // A skip is worthwhile only when the cell width is
                // large enough to offset the escape overhead. Small
                // columns (e.g. " ", ": ", "]") re-emit directly.
                if (bytes_match && this_cells[ci] >= kDeltaMinSkipCells) {
                    pending_skip += this_cells[ci];
                } else {
                    // Flush any accumulated skip run into a single
                    // CUF escape, then emit this column's bytes.
                    if (pending_skip > 0) {
                        append_cursor_right(buf, pending_skip);
                        pending_skip = 0;
                    }
                    buf.append(col_out[ci]);
                    // If this column's cell width differs from the
                    // cached value, every subsequent column's absolute
                    // position shifts — we can still emit them, but
                    // we can no longer skip them via CUF.
                    if (this_cells[ci] != prev_cells[ci]) {
                        positions_stable = false;
                    }
                }
            }
            if (pending_skip > 0) {
                append_cursor_right(buf, pending_skip);
            }
        } else {
            // Full emit: concatenate every visible column's bytes.
            // When use_delta was true globally we skipped the up-front
            // erase, so the previous frame's bytes for this task are
            // still on screen — wipe the row before re-emitting so
            // leftovers past the new content don't linger.
            if (use_delta && st->vt_enabled) buf.append("\x1b[2K", 4);
            for (size_t ci = 0; ci < ncols; ++ci) {
                if (visible_cols[ci]) buf.append(col_out[ci]);
            }
        }

        // Prime the cache for the NEXT frame. Even on the full-emit
        // path we still update the cache so the next frame can diff
        // against a valid baseline.
        for (size_t ci = 0; ci < ncols; ++ci) {
            prev_out[ci]   = col_out[ci];
            prev_cells[ci] = this_cells[ci];
            prev_vis[ci]   = static_cast<uint8_t>(visible_cols[ci]);
        }

        // Measure the task line's cell footprint. Delta-emitted lines
        // may contain CUF escapes which count_display_cells skips over
        // correctly (it treats CSI as zero-width), BUT CUF only moves
        // the cursor — it doesn't add cells. The skipped bytes were
        // already on screen from last frame, so the line still occupies
        // the sum of cells across visible columns.
        int task_cells_total = 0;
        for (size_t ci = 0; ci < ncols; ++ci) {
            if (visible_cols[ci]) task_cells_total += this_cells[ci];
        }
        st->last_task_cells.push_back(task_cells_total);
        // task_start_offset is retained for debugging / future use;
        // we no longer re-measure against buf because col_out now
        // carries the truth.
        (void)task_start_offset;

        if (ctx.snapshot) Py_DECREF(ctx.snapshot);
        visible++;
    }

    if (has_callback) {
        PyGILState_Release(gil_state);
    }

    st->last_rendered_lines = visible > 0 ? visible - 1 : 0;
    st->frame_tick++;
    // Commit the delta cache: the next frame is free to diff against
    // what we just emitted. prev_term_w is captured here so a resize
    // between now and the next render invalidates the cache.
    st->delta_valid = true;
    st->prev_term_w = term_w;
    write_bytes(st, buf.data(), buf.size());
}

void render_loop(ProgressState* st) {
    // Hold render_mtx through the dirty check + render_frame so that
    // tasks/columns/scratch/last_rendered_lines stay coherent vs.
    // add_task / write_above / Progress_close. The hot path
    // (tick/advance/iternext) never touches the mutex — it only writes
    // the per-Task atomic counter, so it is never blocked by render.
    auto interval = std::chrono::duration<double>(st->min_interval);
    std::unique_lock<std::mutex> lock(st->render_mtx);
    while (st->running.load(std::memory_order_acquire)) {
        st->render_cv.wait_for(lock, interval);
        if (!st->running.load(std::memory_order_acquire)) break;

        // Render unconditionally if there is a spinner (it animates even
        // with no producer progress); otherwise only if counters moved.
        // The spinner flag is cached at column setup so we don't re-scan
        // the column vector on every wakeup (every `min_interval`).
        bool any_dirty = st->has_spinner_col;
        if (!any_dirty) {
            for (auto& t : st->tasks) {
                if (t->completed.load(std::memory_order_acquire) != t->last_snapshot) {
                    any_dirty = true;
                    break;
                }
            }
        }
        if (any_dirty) render_frame(st);
    }
    // Final frame, still under the lock.
    render_frame(st);
    if (st->vt_enabled || st->is_console) write_bytes(st, "\n", 1);
}

// -------- Python binding: Progress type --------

struct PyProgress {
    PyObject_HEAD
    ProgressState* state;
};

int parse_columns(PyObject* columns_obj, std::vector<Column>& out) {
    if (columns_obj == nullptr || columns_obj == Py_None) return 0;
    if (!PyList_Check(columns_obj) && !PyTuple_Check(columns_obj)) {
        PyErr_SetString(PyExc_TypeError, "columns must be a list/tuple");
        return -1;
    }
    Py_ssize_t n = PySequence_Fast_GET_SIZE(columns_obj);
    out.clear();
    out.reserve(static_cast<size_t>(n));
    for (Py_ssize_t i = 0; i < n; ++i) {
        PyObject* item = PySequence_Fast_GET_ITEM(columns_obj, i);
        // Accept: 5-tuple (type, text, width, frames, color)
        //     or  6-tuple (type, text, width, frames, color, bar_glyphs)
        //     where bar_glyphs = None | (fill, empty, partials, left, right)
        if (!PyTuple_Check(item)) {
            PyErr_SetString(PyExc_TypeError, "each column must be a tuple");
            return -1;
        }
        Py_ssize_t tlen = PyTuple_GET_SIZE(item);
        if (tlen != 5 && tlen != 6) {
            PyErr_SetString(PyExc_TypeError,
                "each column must be a 5- or 6-tuple");
            return -1;
        }
        Column c;
        PyObject* type_o   = PyTuple_GET_ITEM(item, 0);
        PyObject* text_o   = PyTuple_GET_ITEM(item, 1);
        PyObject* width_o  = PyTuple_GET_ITEM(item, 2);
        PyObject* frames_o = PyTuple_GET_ITEM(item, 3);
        PyObject* color_o  = PyTuple_GET_ITEM(item, 4);

        long type_l = PyLong_AsLong(type_o);
        if (PyErr_Occurred()) return -1;
        c.type = static_cast<int>(type_l);

        if (text_o != Py_None) {
            const char* s = PyUnicode_AsUTF8(text_o);
            if (!s) return -1;
            c.text = s;
        }

        long width_l = PyLong_AsLong(width_o);
        if (PyErr_Occurred()) return -1;
        if (width_l < 0 && static_cast<int>(type_l) == COL_BAR) {
            // Negative width is the flex-bar sentinel from
            // columns.BarColumn(width=None). Store a safe fallback in
            // `width` for the case where the terminal size cannot be
            // queried (piped output, non-TTY, etc.).
            c.flex = true;
            c.width = 40;
        } else {
            c.width = static_cast<int>(width_l);
        }

        if (frames_o != Py_None) {
            if (!PyList_Check(frames_o) && !PyTuple_Check(frames_o)) {
                PyErr_SetString(PyExc_TypeError, "frames must be list/tuple of str");
                return -1;
            }
            Py_ssize_t fn = PySequence_Fast_GET_SIZE(frames_o);
            c.frames.reserve(static_cast<size_t>(fn));
            for (Py_ssize_t j = 0; j < fn; ++j) {
                PyObject* f = PySequence_Fast_GET_ITEM(frames_o, j);
                const char* fs = PyUnicode_AsUTF8(f);
                if (!fs) return -1;
                c.frames.emplace_back(fs);
            }
        }

        if (color_o != Py_None) {
            const char* s = PyUnicode_AsUTF8(color_o);
            if (!s) return -1;
            c.color = s;
        }

        // 6-tuple slot 5 is type-polymorphic:
        //   COL_BAR      → bar glyphs (5-tuple or None)
        //   COL_CALLBACK → Python callable (required, must be callable)
        //   other types  → must be None
        bool glyphs_from_user = false;
        if (tlen == 6 && c.type == COL_CALLBACK) {
            PyObject* cb = PyTuple_GET_ITEM(item, 5);
            if (cb == Py_None || !PyCallable_Check(cb)) {
                PyErr_SetString(PyExc_TypeError,
                    "COL_CALLBACK column requires a callable at slot 5");
                return -1;
            }
            Py_INCREF(cb);
            c.py_callable.assign_new_ref(cb);
        } else if (tlen == 6) {
            PyObject* g = PyTuple_GET_ITEM(item, 5);
            if (g != Py_None) {
                if (!PyTuple_Check(g) || PyTuple_GET_SIZE(g) != 5) {
                    PyErr_SetString(PyExc_TypeError,
                        "bar glyphs must be None or a 5-tuple "
                        "(fill, empty, partials, left, right)");
                    return -1;
                }
                auto pull_str = [&](PyObject* o, std::string& dst) -> int {
                    if (o == Py_None) { dst.clear(); return 0; }
                    const char* s = PyUnicode_AsUTF8(o);
                    if (!s) return -1;
                    dst = s;
                    return 0;
                };
                if (pull_str(PyTuple_GET_ITEM(g, 0), c.fill) < 0) return -1;
                if (pull_str(PyTuple_GET_ITEM(g, 1), c.empty_ch) < 0) return -1;

                PyObject* p = PyTuple_GET_ITEM(g, 2);
                if (p != Py_None) {
                    if (!PyList_Check(p) && !PyTuple_Check(p)) {
                        PyErr_SetString(PyExc_TypeError,
                            "bar partials must be list/tuple of str");
                        return -1;
                    }
                    Py_ssize_t pn = PySequence_Fast_GET_SIZE(p);
                    c.partials.reserve(static_cast<size_t>(pn));
                    for (Py_ssize_t j = 0; j < pn; ++j) {
                        const char* s = PyUnicode_AsUTF8(PySequence_Fast_GET_ITEM(p, j));
                        if (!s) return -1;
                        c.partials.emplace_back(s);
                    }
                }
                if (pull_str(PyTuple_GET_ITEM(g, 3), c.left_border) < 0) return -1;
                if (pull_str(PyTuple_GET_ITEM(g, 4), c.right_border) < 0) return -1;
                glyphs_from_user = true;
            }
        }

        // Bar columns that didn't receive a full glyph spec get defaults.
        if (c.type == COL_BAR && !glyphs_from_user) {
            default_glyphs::apply(c);
        }
        if (c.type == COL_BAR) {
            finalize_bar_cache(c);
        }

        // Callback columns must carry a callable — the Python factory
        // (columns.CallbackColumn) always emits a 6-tuple, so reaching
        // here without one means a hand-built tuple was wrong.
        if (c.type == COL_CALLBACK && !c.py_callable.p) {
            PyErr_SetString(PyExc_TypeError,
                "COL_CALLBACK column must be a 6-tuple with a callable");
            return -1;
        }

        out.push_back(std::move(c));
    }
    return 0;
}

int Progress_init(PyProgress* self, PyObject* args, PyObject* kwds) {
    self->state = new (std::nothrow) ProgressState();
    if (!self->state) {
        PyErr_NoMemory();
        return -1;
    }
    self->state->scratch.reserve(1024);

    PyObject* total_obj = Py_None;
    PyObject* columns_obj = Py_None;
    const char* desc = nullptr;
    double min_interval = 0.05;
    int disable = 0;

    static const char* kwlist[] = {
        "total", "desc", "min_interval", "disable", "columns", nullptr
    };
    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "|OzdpO", const_cast<char**>(kwlist),
            &total_obj, &desc, &min_interval, &disable, &columns_obj)) {
        return -1;
    }
    self->state->min_interval = min_interval;
    self->state->disable = (disable != 0);

    init_console(self->state);

    if (parse_columns(columns_obj, self->state->columns) < 0) return -1;
    if (self->state->columns.empty()) install_default_columns(self->state);
    refresh_column_flags(self->state);

    if (total_obj != Py_None) {
        uint64_t total = PyLong_AsUnsignedLongLong(total_obj);
        if (PyErr_Occurred()) return -1;
        auto task = std::make_unique<Task>();
        task->total = total;
        task->start_time_ns = now_ns();
        if (desc) task->description = desc;
        task->id = 0;
        // Publish task0 before push_back so concurrent tick/advance can
        // see it. We're still single-threaded here (init), but use release
        // semantics so the hot path's acquire load sees a fully-built Task.
        self->state->task0.store(task.get(), std::memory_order_release);
        self->state->tasks.push_back(std::move(task));
    }
    return 0;
}

// Tear down the render thread exactly once, even if invoked from multiple
// threads or via both close() and dealloc.
void close_state(ProgressState* st) {
    std::call_once(st->close_once, [st]() {
        {
            std::lock_guard<std::mutex> lg(st->render_mtx);
            st->running.store(false, std::memory_order_release);
        }
        st->render_cv.notify_all();
        if (st->render_thread.joinable()) {
            st->render_thread.join();
        }
        st->closed = true;
    });
}

void Progress_dealloc(PyProgress* self) {
    if (self->state) {
        close_state(self->state);
        delete self->state;
        self->state = nullptr;
    }
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject*>(self));
}

PyObject* Progress_enter(PyProgress* self, PyObject* /*args*/) {
    auto* st = self->state;
    if (st->disable || st->closed) {
        Py_INCREF(self);
        return reinterpret_cast<PyObject*>(self);
    }
    bool expected = false;
    if (st->running.compare_exchange_strong(
            expected, true,
            std::memory_order_acq_rel, std::memory_order_acquire)) {
        // Synchronous first-frame paint: eliminate the 50ms (min_interval)
        // gap between __enter__ and the render thread's first wakeup.
        // render_frame updates last_snapshot + last_rendered_lines, so the
        // render thread's first tick will see nothing dirty (unless a
        // spinner is present, which always redraws) and won't emit a
        // duplicate frame. The render thread hasn't started yet, so no
        // other thread can be touching state — but we still acquire the
        // render mutex briefly for consistency with every other state
        // mutation path.
        if (!st->columns.empty() && !st->tasks.empty()) {
            std::lock_guard<std::mutex> lg(st->render_mtx);
            render_frame(st);
        }
        try {
            st->render_thread = std::thread(render_loop, st);
        } catch (const std::system_error& e) {
            st->running.store(false, std::memory_order_release);
            PyErr_SetString(PyExc_RuntimeError, e.what());
            return nullptr;
        }
    }
    Py_INCREF(self);
    return reinterpret_cast<PyObject*>(self);
}

PyObject* Progress_close_impl(PyProgress* self) {
    Py_BEGIN_ALLOW_THREADS
    close_state(self->state);
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

PyObject* Progress_exit(PyProgress* self, PyObject* /*args*/) {
    return Progress_close_impl(self);
}

PyObject* Progress_close(PyProgress* self, PyObject* /*args*/) {
    return Progress_close_impl(self);
}

// Hot path: METH_NOARGS +1 on task 0. Lock-free, free-thread safe:
// only touches the cached task0 pointer and its atomic counter.
PyObject* Progress_tick(PyProgress* self, PyObject* /*arg*/) {
    Task* t = self->state->task0.load(std::memory_order_acquire);
    if (BARFLOW_LIKELY(t != nullptr)) {
        t->completed.fetch_add(1, std::memory_order_relaxed);
    }
    Py_RETURN_NONE;
}

// Iteration protocol: `for _ in progress: ...` dispatches via FOR_ITER
// opcode directly to tp_iternext, bypassing CPython's vectorcall trampoline
// that adds ~5 ns to every `progress.tick()` call. This gives tick-style
// users (no source iterable) the same speed as the Tracker wrapper.
//
// Stops when completed >= total on task 0 (if total > 0); otherwise
// yields Py_None forever — the user is responsible for breaking.
PyObject* Progress_iter(PyObject* self) {
    Py_INCREF(self);
    return self;
}

PyObject* Progress_iternext(PyProgress* self) {
    Task* t = self->state->task0.load(std::memory_order_acquire);
    if (BARFLOW_LIKELY(t != nullptr)) {
        uint64_t prev = t->completed.fetch_add(1, std::memory_order_relaxed);
        if (BARFLOW_UNLIKELY(t->total > 0 && prev >= t->total)) {
            // Over-incremented past total — roll back so the final counter
            // reads exactly `total`, then signal end-of-iteration.
            t->completed.fetch_sub(1, std::memory_order_relaxed);
            return nullptr;
        }
    }
    Py_RETURN_NONE;
}

// Fast decode of a PyLong argument to uint64. On CPython 3.12+ small
// ints use the compact representation and we can read the value via
// the internal helpers, avoiding PyLong_AsUnsignedLongLong's overflow
// check and error-path setup. Falls back to the public API for large
// or non-compact ints, and for older CPythons.
// Returns 0 on success and sets `out`. Returns -1 on error (exception set).
static inline int barflow_pylong_to_u64(PyObject* obj, uint64_t* out) {
#if PY_VERSION_HEX >= 0x030C0000
    if (BARFLOW_LIKELY(PyLong_Check(obj))) {
        PyLongObject* lo = reinterpret_cast<PyLongObject*>(obj);
        if (BARFLOW_LIKELY(_PyLong_IsCompact(lo))) {
            Py_ssize_t v = _PyLong_CompactValue(lo);
            if (BARFLOW_LIKELY(v >= 0)) {
                *out = static_cast<uint64_t>(v);
                return 0;
            }
            // Negative compact int — let the slow path raise OverflowError.
        }
    }
#endif
    uint64_t v = PyLong_AsUnsignedLongLong(obj);
    if (v == static_cast<uint64_t>(-1) && PyErr_Occurred()) return -1;
    *out = v;
    return 0;
}

// Hot path: METH_FASTCALL advance(n=1) on task 0. Lock-free.
PyObject* Progress_advance(PyProgress* self,
                           PyObject* const* args,
                           Py_ssize_t nargs) {
    uint64_t n = 1;
    if (nargs >= 1) {
        if (BARFLOW_UNLIKELY(barflow_pylong_to_u64(args[0], &n) < 0)) {
            return nullptr;
        }
    }
    Task* t = self->state->task0.load(std::memory_order_acquire);
    if (BARFLOW_LIKELY(t != nullptr)) {
        t->completed.fetch_add(n, std::memory_order_relaxed);
    }
    Py_RETURN_NONE;
}

// Multi-task form: update(task_id, n=1). Locks the vector for index
// lookup; per-task counter remains atomic.
PyObject* Progress_update(PyProgress* self,
                          PyObject* const* args,
                          Py_ssize_t nargs) {
    if (nargs < 1 || nargs > 2) {
        PyErr_SetString(PyExc_TypeError, "update(task_id, n=1)");
        return nullptr;
    }
    long task_id = PyLong_AsLong(args[0]);
    if (PyErr_Occurred()) return nullptr;
    uint64_t n = 1;
    if (nargs >= 2) {
        if (barflow_pylong_to_u64(args[1], &n) < 0) return nullptr;
    }
    Task* target = nullptr;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        if (task_id < 0 ||
            static_cast<size_t>(task_id) >= self->state->tasks.size()) {
            PyErr_SetString(PyExc_IndexError, "task_id out of range");
            return nullptr;
        }
        target = self->state->tasks[static_cast<size_t>(task_id)].get();
    }
    target->completed.fetch_add(n, std::memory_order_relaxed);
    Py_RETURN_NONE;
}

PyObject* Progress_add_task(PyProgress* self, PyObject* args, PyObject* kwds) {
    static const char* kwlist[] = {"total", "desc", nullptr};
    PyObject* total_obj = Py_None;
    const char* desc = nullptr;
    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "|Oz", const_cast<char**>(kwlist),
            &total_obj, &desc)) {
        return nullptr;
    }
    auto task = std::make_unique<Task>();
    if (total_obj != Py_None) {
        task->total = PyLong_AsUnsignedLongLong(total_obj);
        if (PyErr_Occurred()) return nullptr;
    }
    task->start_time_ns = now_ns();
    if (desc) task->description = desc;
    Task* raw = task.get();
    int id;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        id = static_cast<int>(self->state->tasks.size());
        task->id = id;
        self->state->tasks.push_back(std::move(task));
        // Publish task0 if this is the first task. CAS so concurrent
        // first-add races resolve to whichever wins.
        Task* expected = nullptr;
        self->state->task0.compare_exchange_strong(
            expected, raw,
            std::memory_order_release, std::memory_order_relaxed);
    }
    return PyLong_FromLong(id);
}

// set_total(task_id, total) — update an existing task's total. Takes
// render_mtx because the render thread reads `task->total` under that
// lock. Wakes the render cv so the next frame reflects the new total.
PyObject* Progress_set_total(PyProgress* self,
                             PyObject* const* args,
                             Py_ssize_t nargs) {
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "set_total(task_id, total)");
        return nullptr;
    }
    long task_id = PyLong_AsLong(args[0]);
    if (PyErr_Occurred()) return nullptr;
    uint64_t total = 0;
    if (barflow_pylong_to_u64(args[1], &total) < 0) return nullptr;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        if (task_id < 0 ||
            static_cast<size_t>(task_id) >= self->state->tasks.size()) {
            PyErr_SetString(PyExc_IndexError, "task_id out of range");
            return nullptr;
        }
        self->state->tasks[static_cast<size_t>(task_id)]->total = total;
    }
    self->state->render_cv.notify_one();
    Py_RETURN_NONE;
}

// set_task_description(task_id, desc) — update the task's description
// string. Same locking discipline as set_total: the render thread reads
// description under render_mtx while formatting COL_DESC, so grabbing
// the mutex here serializes the swap. The hot path (tick/advance) is
// unaffected — it only touches the atomic `completed` counter.
PyObject* Progress_set_task_description(PyProgress* self,
                                        PyObject* const* args,
                                        Py_ssize_t nargs) {
    if (nargs != 2) {
        PyErr_SetString(PyExc_TypeError, "set_task_description(task_id, desc)");
        return nullptr;
    }
    long task_id = PyLong_AsLong(args[0]);
    if (PyErr_Occurred()) return nullptr;
    if (!PyUnicode_Check(args[1])) {
        PyErr_SetString(PyExc_TypeError, "desc must be str");
        return nullptr;
    }
    Py_ssize_t dlen = 0;
    const char* ds = PyUnicode_AsUTF8AndSize(args[1], &dlen);
    if (!ds) return nullptr;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        if (task_id < 0 ||
            static_cast<size_t>(task_id) >= self->state->tasks.size()) {
            PyErr_SetString(PyExc_IndexError, "task_id out of range");
            return nullptr;
        }
        self->state->tasks[static_cast<size_t>(task_id)]->description.assign(
            ds, static_cast<size_t>(dlen));
    }
    self->state->render_cv.notify_one();
    Py_RETURN_NONE;
}

// set_description(desc) — update task 0's description. Convenience
// wrapper around set_task_description for the common single-task case.
PyObject* Progress_set_description(PyProgress* self, PyObject* desc_obj) {
    if (!PyUnicode_Check(desc_obj)) {
        PyErr_SetString(PyExc_TypeError, "desc must be str");
        return nullptr;
    }
    Py_ssize_t dlen = 0;
    const char* ds = PyUnicode_AsUTF8AndSize(desc_obj, &dlen);
    if (!ds) return nullptr;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        if (self->state->tasks.empty()) {
            PyErr_SetString(PyExc_IndexError, "no tasks");
            return nullptr;
        }
        self->state->tasks[0]->description.assign(
            ds, static_cast<size_t>(dlen));
    }
    self->state->render_cv.notify_one();
    Py_RETURN_NONE;
}

// refresh() — force an immediate render. Useful when the caller wants
// to flush the current state (e.g. after a burst of updates) without
// waiting for the next scheduled tick. Drops the GIL around the render
// so callback columns can reacquire it via PyGILState_Ensure.
PyObject* Progress_refresh(PyProgress* self, PyObject* /*arg*/) {
    auto* st = self->state;
    Py_BEGIN_ALLOW_THREADS
    {
        std::lock_guard<std::mutex> lg(st->render_mtx);
        render_frame(st);
    }
    st->render_cv.notify_one();
    Py_END_ALLOW_THREADS
    Py_RETURN_NONE;
}

PyObject* Progress_write_above(PyProgress* self, PyObject* text_obj) {
    if (!PyUnicode_Check(text_obj)) {
        PyErr_SetString(PyExc_TypeError, "write_above expects str");
        return nullptr;
    }
    Py_ssize_t len = 0;
    const char* text = PyUnicode_AsUTF8AndSize(text_obj, &len);
    if (!text) return nullptr;

    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        auto* st = self->state;
        std::string& buf = st->scratch;
        buf.clear();

        // Walk up through whatever physical rows the previous bar area
        // currently occupies at the *current* terminal width so a live
        // resize between frames is handled the same way render_frame
        // handles it.
        int term_w = query_terminal_width(st);
        if (!st->last_task_cells.empty() && st->vt_enabled) {
            int total_rows = 0;
            for (int c : st->last_task_cells) {
                int r;
                if (term_w > 0) {
                    r = (c + term_w - 1) / term_w;
                    if (r < 1) r = 1;
                } else {
                    r = 1;
                }
                total_rows += r;
            }
            if (total_rows > 0) {
                buf.append("\x1b[", 2);
                char tmp[20];
                size_t n = u64_to_chars(tmp, static_cast<uint64_t>(total_rows));
                buf.append(tmp, n);
                buf.push_back('A');
            }
        }
        buf.push_back('\r');
        if (st->vt_enabled) buf.append("\x1b[J", 3);
        buf.append(text, static_cast<size_t>(len));
        // Ensure the emitted text ends with a CRLF so the cursor returns
        // to column 0 on Windows (where LF alone doesn't auto-CR when
        // VT processing is on).
        if (len == 0 || text[len - 1] != '\n') {
            buf.append("\r\n", 2);
        } else if (len < 2 || text[len - 2] != '\r') {
            buf[buf.size() - 1] = '\r';
            buf.push_back('\n');
        }
        write_bytes(st, buf.data(), buf.size());
        st->last_rendered_lines = 0;
        st->last_task_cells.clear();
        // write_above moved the cursor and emitted unrelated content
        // on what used to be the bar area. The delta cache describes
        // bytes that are no longer on screen where it thinks they are
        // — invalidate so the next render_frame does a full emit.
        st->delta_valid = false;
    }
    self->state->render_cv.notify_one();
    Py_RETURN_NONE;
}

PyObject* Progress_get_completed(PyProgress* self, void* /*closure*/) {
    Task* t = self->state->task0.load(std::memory_order_acquire);
    uint64_t v = t ? t->completed.load(std::memory_order_relaxed) : 0;
    return PyLong_FromUnsignedLongLong(v);
}

PyObject* Progress_get_n_tasks(PyProgress* self, void* /*closure*/) {
    Py_ssize_t n;
    {
        std::lock_guard<std::mutex> lg(self->state->render_mtx);
        n = static_cast<Py_ssize_t>(self->state->tasks.size());
    }
    return PyLong_FromSsize_t(n);
}

PyMethodDef Progress_methods[] = {
    {"__enter__",  reinterpret_cast<PyCFunction>(Progress_enter),   METH_NOARGS,  nullptr},
    {"__exit__",   reinterpret_cast<PyCFunction>(Progress_exit),    METH_VARARGS, nullptr},
    {"close",      reinterpret_cast<PyCFunction>(Progress_close),   METH_NOARGS,  nullptr},
    {"tick",       reinterpret_cast<PyCFunction>(Progress_tick),    METH_NOARGS,
        "Fast path: increment task 0 by 1."},
    {"advance",    reinterpret_cast<PyCFunction>(Progress_advance), METH_FASTCALL,
        "advance(n=1) — increment task 0 by n."},
    {"update",     reinterpret_cast<PyCFunction>(Progress_update),  METH_FASTCALL,
        "update(task_id, n=1) — multi-task form."},
    {"add_task",   reinterpret_cast<PyCFunction>(Progress_add_task),
        METH_VARARGS | METH_KEYWORDS,
        "add_task(total=None, desc=None) -> task_id."},
    {"set_total",  reinterpret_cast<PyCFunction>(Progress_set_total),  METH_FASTCALL,
        "set_total(task_id, total) — update a task's total count."},
    {"set_description", reinterpret_cast<PyCFunction>(Progress_set_description),
        METH_O,
        "set_description(desc) — update task 0's description."},
    {"set_task_description",
        reinterpret_cast<PyCFunction>(Progress_set_task_description),
        METH_FASTCALL,
        "set_task_description(task_id, desc) — update a task's description."},
    {"refresh",    reinterpret_cast<PyCFunction>(Progress_refresh),    METH_NOARGS,
        "Force an immediate render frame."},
    {"write_above",reinterpret_cast<PyCFunction>(Progress_write_above),
        METH_O, "Emit text above the bar area without tearing."},
    {nullptr, nullptr, 0, nullptr}
};

PyGetSetDef Progress_getset[] = {
    {"completed", reinterpret_cast<getter>(Progress_get_completed), nullptr, nullptr, nullptr},
    {"n_tasks",   reinterpret_cast<getter>(Progress_get_n_tasks),   nullptr, nullptr, nullptr},
    {nullptr, nullptr, nullptr, nullptr, nullptr}
};

PyTypeObject ProgressType = { PyVarObject_HEAD_INIT(nullptr, 0) };

// -------- Python binding: Tracker type --------

struct PyTracker {
    PyObject_HEAD
    PyObject*    iterator;
    PyProgress*  progress;
    Task*        task;
    // Cached tp_iternext of self->iterator's type. Populated in
    // Tracker_init so the hot path doesn't have to re-deref the
    // type object's slot each iteration. Initialized to PyIter_Next
    // as a safe fallback so the hot path can dispatch unconditionally
    // without a null check.
    iternextfunc iternext_slot;
    int          closed;
    int          owns_progress;  // close progress on exhaust
};

int Tracker_init(PyTracker* self, PyObject* args, PyObject* kwds) {
    PyObject* iterator;
    PyObject* progress;
    int task_id = 0;
    int owns = 1;
    static const char* kwlist[] = {"iterator", "progress", "task_id", "owns_progress", nullptr};
    if (!PyArg_ParseTupleAndKeywords(
            args, kwds, "OO|ip", const_cast<char**>(kwlist),
            &iterator, &progress, &task_id, &owns)) {
        return -1;
    }
    if (!PyObject_TypeCheck(progress, &ProgressType)) {
        PyErr_SetString(PyExc_TypeError, "progress must be a Progress instance");
        return -1;
    }
    Py_INCREF(iterator);
    self->iterator = iterator;
    // Cache the iterator type's tp_iternext slot. Most real iterators
    // (generators, list_iterator, range_iterator, ...) have this set and
    // we can call it directly, skipping the PyIter_Next wrapper's type
    // check + slot lookup on every step. Fall back to PyIter_Next as a
    // default function so the hot path can dispatch unconditionally
    // without a null check.
    iternextfunc slot = Py_TYPE(iterator)->tp_iternext;
    self->iternext_slot = slot ? slot : PyIter_Next;
    Py_INCREF(progress);
    self->progress = reinterpret_cast<PyProgress*>(progress);

    {
        // Lock the vector for the lookup. The Task* itself is heap-stable
        // (unique_ptr) so the cached pointer remains valid for the
        // lifetime of the Progress instance.
        auto* st = self->progress->state;
        std::lock_guard<std::mutex> lg(st->render_mtx);
        if (st->tasks.empty()) {
            PyErr_SetString(PyExc_RuntimeError, "progress has no tasks");
            return -1;
        }
        if (task_id < 0 || static_cast<size_t>(task_id) >= st->tasks.size()) {
            PyErr_SetString(PyExc_IndexError, "task_id out of range");
            return -1;
        }
        self->task = st->tasks[static_cast<size_t>(task_id)].get();
    }
    self->closed = 0;
    self->owns_progress = owns;
    return 0;
}

void Tracker_dealloc(PyTracker* self) {
    if (!self->closed && self->progress && self->owns_progress) {
        PyObject* r = Progress_close_impl(self->progress);
        Py_XDECREF(r);
        self->closed = 1;
    }
    Py_XDECREF(self->iterator);
    Py_XDECREF(self->progress);
    Py_TYPE(self)->tp_free(reinterpret_cast<PyObject*>(self));
}

PyObject* Tracker_iter(PyTracker* self) {
    Py_INCREF(self);
    return reinterpret_cast<PyObject*>(self);
}

PyObject* Tracker_iternext(PyTracker* self) {
    // Call the cached tp_iternext slot directly. The slot is always
    // populated in Tracker_init (falling back to PyIter_Next for
    // objects that lack tp_iternext), so no null check is needed here.
    // If the slot returns NULL with no exception set that means
    // "exhausted"; NULL with an exception set is a real error. Either
    // way we treat it as end-of-iteration — the caller (Python) will
    // re-raise any pending exception.
    PyObject* nxt = self->iternext_slot(self->iterator);
    if (BARFLOW_UNLIKELY(nxt == nullptr)) {
        if (!self->closed && self->progress && self->owns_progress) {
            self->closed = 1;
            PyObject* r = Progress_close_impl(self->progress);
            Py_XDECREF(r);
        }
        return nullptr;
    }
    if (BARFLOW_LIKELY(self->task != nullptr)) {
        self->task->completed.fetch_add(1, std::memory_order_relaxed);
    }
    return nxt;
}

PyTypeObject TrackerType = { PyVarObject_HEAD_INIT(nullptr, 0) };

// -------- Module init --------

PyModuleDef moduledef = {
    PyModuleDef_HEAD_INIT,
    "barflow._core",
    "C++ core for BarFlow.",
    -1,
    nullptr, nullptr, nullptr, nullptr, nullptr
};

}  // anon namespace

extern "C" PyMODINIT_FUNC PyInit__core(void) {
    ProgressType.tp_name      = "barflow._core.Progress";
    ProgressType.tp_basicsize = sizeof(PyProgress);
    ProgressType.tp_dealloc   = reinterpret_cast<destructor>(Progress_dealloc);
    ProgressType.tp_flags     = Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE;
    ProgressType.tp_doc       = "Progress bar with multi-task + columns.";
    ProgressType.tp_methods   = Progress_methods;
    ProgressType.tp_getset    = Progress_getset;
    ProgressType.tp_init      = reinterpret_cast<initproc>(Progress_init);
    ProgressType.tp_new       = PyType_GenericNew;
    ProgressType.tp_iter      = reinterpret_cast<getiterfunc>(Progress_iter);
    ProgressType.tp_iternext  = reinterpret_cast<iternextfunc>(Progress_iternext);
    if (PyType_Ready(&ProgressType) < 0) return nullptr;

    TrackerType.tp_name      = "barflow._core.Tracker";
    TrackerType.tp_basicsize = sizeof(PyTracker);
    TrackerType.tp_dealloc   = reinterpret_cast<destructor>(Tracker_dealloc);
    TrackerType.tp_flags     = Py_TPFLAGS_DEFAULT;
    TrackerType.tp_doc       = "Fast iterator wrapper bound to a Progress task.";
    TrackerType.tp_iter      = reinterpret_cast<getiterfunc>(Tracker_iter);
    TrackerType.tp_iternext  = reinterpret_cast<iternextfunc>(Tracker_iternext);
    TrackerType.tp_init      = reinterpret_cast<initproc>(Tracker_init);
    TrackerType.tp_new       = PyType_GenericNew;
    if (PyType_Ready(&TrackerType) < 0) return nullptr;

    PyObject* m = PyModule_Create(&moduledef);
    if (!m) return nullptr;

    // Declare the module safe for the free-threaded (no-GIL) build.
    // Without this, importing under a free-threaded interpreter would
    // re-enable the GIL for the whole process. All shared state is
    // protected by render_mtx and the producer hot path is lock-free
    // via std::atomic, so we are GIL-not-used safe.
#ifdef Py_GIL_DISABLED
    PyUnstable_Module_SetGIL(m, Py_MOD_GIL_NOT_USED);
#endif

    Py_INCREF(&ProgressType);
    if (PyModule_AddObject(m, "Progress",
                           reinterpret_cast<PyObject*>(&ProgressType)) < 0) {
        Py_DECREF(&ProgressType); Py_DECREF(m); return nullptr;
    }
    Py_INCREF(&TrackerType);
    if (PyModule_AddObject(m, "Tracker",
                           reinterpret_cast<PyObject*>(&TrackerType)) < 0) {
        Py_DECREF(&TrackerType); Py_DECREF(m); return nullptr;
    }

    // Column type enum
    PyModule_AddIntConstant(m, "COL_TEXT",        COL_TEXT);
    PyModule_AddIntConstant(m, "COL_DESCRIPTION", COL_DESCRIPTION);
    PyModule_AddIntConstant(m, "COL_BAR",         COL_BAR);
    PyModule_AddIntConstant(m, "COL_PERCENT",     COL_PERCENT);
    PyModule_AddIntConstant(m, "COL_COUNT",       COL_COUNT);
    PyModule_AddIntConstant(m, "COL_RATE",        COL_RATE);
    PyModule_AddIntConstant(m, "COL_ELAPSED",     COL_ELAPSED);
    PyModule_AddIntConstant(m, "COL_ETA",         COL_ETA);
    PyModule_AddIntConstant(m, "COL_SPINNER",     COL_SPINNER);
    PyModule_AddIntConstant(m, "COL_CALLBACK",    COL_CALLBACK);

    // `g_simple_namespace` is loaded lazily on first CallbackColumn render
    // (see ensure_simple_namespace) so cold import doesn't pay for
    // `import types`. The empty args tuple stays eager — free to allocate
    // and reused across every PyObject_Call.
    g_empty_tuple = PyTuple_New(0);
    if (!g_empty_tuple) { Py_DECREF(m); return nullptr; }

    return m;
}
