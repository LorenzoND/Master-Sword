"""Monta o texto do overlay a partir de um Snapshot.

Duas saídas a partir dos mesmos itens:
- `rtss_text`: hypertext do RTSS (tags de cor/tamanho/alinhamento, macros <FR>/<FT>)
- `plain_lines`: linhas simples pro overlay de desktop e pra prévia na janela
"""

from typing import Optional

from core.ec import FAN_MODE_LABELS
from core.sampler import Snapshot
from core.settings import Settings

ALERT_COLOR = "FF4D4D"


def _fmt(value, spec: str = ".0f") -> str:
    return "--" if value is None else format(value, spec)


def _rows(snap: Snapshot, s: Settings) -> list[tuple[str, list[tuple[str, str]], list[str]]]:
    """[(rótulo, [(valor, unidade)], [limites])] — formato neutro usado pelas duas saídas."""
    on = s.overlay_items
    rows = []

    g = snap.gpu
    gpu_vals = []
    if on["gpu_temp"]:
        gpu_vals.append((_fmt(snap.gpu_temp), "°C"))
    if g:
        if on["gpu_usage"]:
            gpu_vals.append((_fmt(g["util_pct"]), "%"))
        if on["gpu_clock"]:
            gpu_vals.append((_fmt(g["clock_mhz"]), "MHz"))
        if on["gpu_power"]:
            gpu_vals.append((_fmt(g["power_w"]), "W"))
        if on["gpu_vram"]:
            gpu_vals.append((_fmt(g["mem_used_mb"] / 1024, ".1f"), "GB"))
    gpu_lim = (g or {}).get("limits", []) if on["gpu_limit"] else []
    if gpu_vals or gpu_lim:
        rows.append(("GPU", gpu_vals, gpu_lim))

    c = snap.cpu
    cpu_vals = []
    if on["cpu_temp"]:
        cpu_vals.append((_fmt(snap.cpu_temp), "°C"))
    if on["cpu_usage"]:
        cpu_vals.append((_fmt(c.get("load_pct")), "%"))
    if on["cpu_clock"] and c.get("clock_mhz"):
        cpu_vals.append((_fmt(c["clock_mhz"] / 1000, ".1f"), "GHz"))
    if on["cpu_power"]:
        cpu_vals.append((_fmt(c.get("power_w")), "W"))
    cpu_lim = (snap.cpu_limits or {}).get("limits", []) if on["cpu_limit"] else []
    if cpu_vals or cpu_lim:
        rows.append(("CPU", cpu_vals, cpu_lim))

    if on["cpu_cores"] and c.get("core_loads"):
        rows.append(("CORE", [(_fmt(v), "") for v in c["core_loads"]], []))

    if on["ram"]:
        rows.append(("RAM", [(_fmt(snap.ram_used_gb, ".1f"), "GB")], []))

    if on["fans"] and snap.ec:
        e = snap.ec
        fan_vals = []
        for key in ("cpu", "gpu"):
            rpm = e.get(f"{key}_fan_rpm")
            fan_vals.append((str(rpm), "rpm") if rpm else (_fmt(e[f"{key}_fan_pct"]), "%"))
        tags = ["BOOST"] if e.get("cooler_boost") else []
        rows.append(("FAN", fan_vals, tags))
    return rows


def rtss_text(snap: Snapshot, s: Settings, alert_gpu: bool, alert_cpu: bool) -> str:
    color = s.overlay_color
    out = [f"<C0={color}><C1={ALERT_COLOR}><S0=-50><A0=-4>"]
    for label, vals, tags in _rows(snap, s):
        alert = (label == "GPU" and alert_gpu) or (label == "CPU" and alert_cpu)
        c = "<C1>" if alert else "<C0>"
        parts = [f"{c}{label}<C>"]
        for v, unit in vals:
            parts.append(f"{c}<A0>{v}<A><S0>{unit}<S><C>")
        if tags:
            parts.append(f"<C1>{' '.join(t.upper().replace('É', 'E') for t in tags)}<C>")
        out.append(" ".join(parts) + "\n")
    if s.overlay_items["fps"]:
        out.append("<C0>FPS<C> <C0><A0><FR><A><S0>fps<S> <A0><FT><A><S0>ms<S><C>\n")
    if s.overlay_items["frametime_graph"]:
        out.append("<C0><OBJ=00000000><C>\n")
    return "".join(out)


def plain_lines(snap: Optional[Snapshot], s: Settings, alert_gpu: bool = False,
                alert_cpu: bool = False) -> list[tuple[str, bool]]:
    """[(texto, em_alerta)] pro overlay de desktop / prévia."""
    if snap is None:
        return [("aguardando sensores...", False)]
    lines = []
    for label, vals, tags in _rows(snap, s):
        alert = (label == "GPU" and alert_gpu) or (label == "CPU" and alert_cpu) or bool(
            tags and label in ("GPU", "CPU"))
        text = f"{label:<4} " + "  ".join(f"{v}{unit}" if unit in ("%", "°C") else f"{v} {unit}".strip()
                                          for v, unit in vals)
        if tags:
            text += "  " + " ".join(t.upper() for t in tags)
        lines.append((text, alert))
    if s.overlay_items["fps"]:
        if snap.game:
            lines.append((f"FPS  {snap.game['fps']:.0f}  {snap.game['frametime_ms']:.1f} ms", False))
        else:
            lines.append(("FPS  -- (precisa do RTSS aberto)", False))
    return lines


def fan_mode_label(snap: Snapshot) -> str:
    if not snap.ec:
        return "--"
    mode = snap.ec.get("fan_mode")
    return FAN_MODE_LABELS.get(mode, f"0x{snap.ec['fan_mode_raw']:02X}") if mode else f"0x{snap.ec['fan_mode_raw']:02X}"
