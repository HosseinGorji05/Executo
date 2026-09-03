/* Executo — client-side tickers.
 *
 * The server re-renders the run panel and the session chip as plain HTML on
 * every agent event, which is far too coarse for a clock. So the server emits
 * *relative* seconds on data attributes and this script animates them locally.
 *
 * Anchoring is keyed, not per-element: Gradio patches attributes in place and
 * reuses the DOM node, so "first time we saw this element" would latch onto
 * the page-load value forever. Instead each element carries a data-ex-key that
 * changes whenever the server issues a new value, and we re-anchor on that.
 *
 *   [data-ex-elapsed="12.4"]   count up from 12.4s   (run timer)
 *     + [data-ex-running]  "0" freezes it at the server value
 *   [data-ex-countdown="23.4"] count down to zero    (cooldown)
 *     + [data-ex-total]  denominator for the drain bar
 *     + [data-ex-ready]  label to show once it hits zero
 */
(function () {
    "use strict";

    var TICK_MS = 100;
    var scrolledRun = null;

    function pad(n) {
        return (n < 10 ? "0" : "") + n;
    }

    function clock(seconds) {
        var s = Math.max(0, Math.floor(seconds));
        return pad(Math.floor(s / 60)) + ":" + pad(s % 60);
    }

    // True the first time this element is seen carrying this key.
    function reanchored(el, key) {
        if (el.__exKey === key) return false;
        el.__exKey = key;
        return true;
    }

    function tickElapsed(now) {
        var nodes = document.querySelectorAll("[data-ex-elapsed]");
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            var value = parseFloat(el.dataset.exElapsed) || 0;
            if (el.dataset.exRunning === "0") {
                el.__exKey = null; // re-anchor if this panel starts running again
                el.textContent = clock(value);
                continue;
            }
            if (reanchored(el, el.dataset.exKey)) el.__exBase = now - value * 1000;
            el.textContent = clock((now - el.__exBase) / 1000);
        }
    }

    function tickCountdown(now) {
        var nodes = document.querySelectorAll("[data-ex-countdown]");
        for (var i = 0; i < nodes.length; i++) {
            var el = nodes[i];
            if (reanchored(el, el.dataset.exKey)) {
                el.__exEnd = now + (parseFloat(el.dataset.exCountdown) || 0) * 1000;
            }
            var left = Math.max(0, (el.__exEnd - now) / 1000);
            var total = parseFloat(el.dataset.exTotal) || 0;
            var chip = el.closest(".ex-chip");
            var bar = chip && chip.querySelector(".ex-chip-bar i");

            if (left <= 0.05) {
                el.textContent = el.dataset.exReady || "Ready";
                if (chip && chip.dataset.state === "cooling") chip.dataset.state = "ready";
                if (bar) bar.style.width = "0%";
            } else {
                el.textContent = "Ready in " + Math.ceil(left) + "s";
                if (bar && total > 0) bar.style.width = (left / total) * 100 + "%";
            }
        }
    }

    // Keep the newest step visible without yanking the page around.
    function tickSteps() {
        var lists = document.querySelectorAll(".ex-steps");
        for (var i = 0; i < lists.length; i++) {
            var el = lists[i];
            if (el.scrollHeight > el.clientHeight) el.scrollTop = el.scrollHeight;
        }
    }

    // Bring the run panel into view once per run, and only if it is off-screen.
    function tickScroll() {
        var panel = document.querySelector(".ex-run[data-run-id]");
        if (!panel) return;
        var id = panel.dataset.runId;
        if (id === scrolledRun) return;
        scrolledRun = id;
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function tick() {
        var now = performance.now();
        tickElapsed(now);
        tickCountdown(now);
        tickSteps();
        tickScroll();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", tick);
    }
    setInterval(tick, TICK_MS);
    tick();
})();
