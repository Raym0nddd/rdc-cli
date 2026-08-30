"""Pixel handlers: pixel_history, pick_pixel."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from rdc.handlers._helpers import (
    PipeError,
    _error_response,
    _result_response,
    require_pipe,
)
from rdc.handlers._types import Handler

if TYPE_CHECKING:
    from rdc.daemon_server import DaemonState

_FLAG_ATTRS = [
    "directShaderWrite",
    "unboundPS",
    "sampleMasked",
    "backfaceCulled",
    "depthClipped",
    "scissorClipped",
    "shaderDiscarded",
    "depthTestFailed",
    "stencilTestFailed",
    "depthBoundsFailed",
    "predicationSkipped",
    "viewClipped",
]

_TYPE_CASTS = {
    "typeless": "Typeless",
    "float": "Float",
    "unorm": "UNorm",
    "snorm": "SNorm",
    "uint": "UInt",
    "sint": "SInt",
    "uscaled": "UScaled",
    "sscaled": "SScaled",
    "depth": "Depth",
    "unormsrgb": "UNormSRGB",
}


class PixelSelectionError(ValueError):
    def __init__(self, message: str, code: int = -32001) -> None:
        super().__init__(message)
        self.code = code


def _safe_depth(d: float) -> float | None:
    """Return None for sentinel / non-finite depth values."""
    if d == -1.0 or not math.isfinite(d):
        return None
    return d


def _rgba(col: Any) -> dict[str, float]:
    v = col.floatValue
    return {"r": v[0], "g": v[1], "b": v[2], "a": v[3]}


def _collect_flags(mod: Any) -> list[str]:
    return [name for name in _FLAG_ATTRS if getattr(mod, name, False)]


def _mod_to_dict(mod: Any) -> dict[str, Any]:
    return {
        "eid": mod.eventId,
        "fragment": mod.fragIndex,
        "primitive": mod.primitiveID,
        "shader_out": _rgba(mod.shaderOut.col),
        "post_mod": _rgba(mod.postMod.col),
        "depth": _safe_depth(mod.postMod.depth),
        "passed": mod.Passed(),
        "flags": _collect_flags(mod),
    }


def _resolve_texture_selection(
    params: dict[str, Any], state: DaemonState, pipe: Any, x: int, y: int
) -> tuple[Any, int | None, Any, Any, Any, str]:
    """Resolve and validate a texture, subresource, and component interpretation."""
    has_target = "target" in params and params["target"] is not None
    has_resource = "resource_id" in params and params["resource_id"] is not None
    if has_target and has_resource:
        raise PixelSelectionError(
            "target and resource_id are mutually exclusive",
            code=-32602,
        )

    target_idx: int | None = None
    if has_resource:
        resource_id = int(params["resource_id"])
        tex = state.tex_map.get(resource_id)
        if tex is None:
            raise PixelSelectionError(f"texture resource {resource_id} not found")
        texture_resource = tex.resourceId
        selection_source = "resource-id"
    else:
        target_idx = int(params.get("target", 0))
        targets = pipe.GetOutputTargets()
        non_null = [(i, target) for i, target in enumerate(targets) if int(target.resource) != 0]
        if not non_null:
            raise PixelSelectionError("no color targets at the selected event")
        match = [target for i, target in non_null if i == target_idx]
        if not match:
            raise PixelSelectionError(f"target index {target_idx} out of range")
        texture_resource = match[0].resource
        tex = state.tex_map.get(int(texture_resource))
        if tex is None:
            raise PixelSelectionError(f"texture resource {int(texture_resource)} not found")
        selection_source = "output-target"

    mip = int(params.get("mip", 0))
    array_slice = int(params.get("slice", 0))
    sample = int(params.get("sample", 0))
    mip_count = max(1, int(getattr(tex, "mips", 1)))
    if not 0 <= mip < mip_count:
        raise PixelSelectionError(f"mip {mip} out of range [0, {mip_count})")

    rd = state.rd
    is_3d = rd is not None and tex.type == rd.TextureType.Texture3D
    if is_3d:
        slice_count = max(1, int(tex.depth) >> mip)
    else:
        slice_count = max(1, int(getattr(tex, "arraysize", 1)))
    if not 0 <= array_slice < slice_count:
        raise PixelSelectionError(f"slice {array_slice} out of range [0, {slice_count})")

    sample_count = max(1, int(getattr(tex, "msSamp", 1)))
    if not 0 <= sample < sample_count:
        raise PixelSelectionError(f"sample {sample} out of range [0, {sample_count})")

    mip_width = max(1, int(tex.width) >> mip)
    mip_height = max(1, int(tex.height) >> mip)
    if not (0 <= x < mip_width and 0 <= y < mip_height):
        raise PixelSelectionError(
            f"coordinates ({x}, {y}) out of bounds for mip {mip} "
            f"[{mip_width}x{mip_height}]"
        )

    requested_type_cast = str(params.get("type_cast", "Typeless"))
    canonical_type_cast = _TYPE_CASTS.get(requested_type_cast.casefold())
    if canonical_type_cast is None:
        raise PixelSelectionError(
            f"unsupported type_cast: {requested_type_cast}",
            code=-32602,
        )

    subresource = rd.Subresource()
    subresource.mip = mip
    subresource.slice = array_slice
    subresource.sample = sample
    comp_type = getattr(rd.CompType, canonical_type_cast)
    return (
        texture_resource,
        target_idx,
        subresource,
        comp_type,
        tex,
        selection_source,
    )


def _handle_pixel_history(
    request_id: int, params: dict[str, Any], state: DaemonState
) -> tuple[dict[str, Any], bool]:
    """Handle pixel_history JSON-RPC request.

    Args:
        request_id: JSON-RPC request id.
        params: Request parameters for the event, texture, subresource, and pixel.
        state: Daemon state with adapter and tex_map.

    Returns:
        Tuple of (response dict, keep_running bool).
    """
    for key in ("x", "y"):
        if key not in params:
            return _error_response(request_id, -32602, f"missing required param: {key}"), True

    x = int(params["x"])
    y = int(params["y"])

    try:
        eid, pipe = require_pipe(params, state, request_id)
    except PipeError as exc:
        return exc.response, True

    try:
        rt_rid, target_idx, sub, comp_type, _, selection_source = _resolve_texture_selection(
            params, state, pipe, x, y
        )
    except (PixelSelectionError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, PixelSelectionError) else -32602
        return _error_response(request_id, code, str(error)), True

    controller = state.adapter.controller  # type: ignore[union-attr]
    mods = controller.PixelHistory(rt_rid, x, y, sub, comp_type)

    return _result_response(
        request_id,
        {
            "x": x,
            "y": y,
            "eid": eid,
            "target": {"index": target_idx, "id": int(rt_rid)},
            "resource": {
                "id": int(rt_rid),
                "selection": selection_source,
                "targetIndex": target_idx,
            },
            "subresource": {"mip": sub.mip, "slice": sub.slice, "sample": sub.sample},
            "typeCast": _TYPE_CASTS[str(params.get("type_cast", "Typeless")).casefold()],
            "modifications": [_mod_to_dict(m) for m in mods],
        },
    ), True


def _handle_pick_pixel(
    request_id: int, params: dict[str, Any], state: DaemonState
) -> tuple[dict[str, Any], bool]:
    """Handle pick_pixel JSON-RPC request.

    Args:
        request_id: JSON-RPC request id.
        params: Request parameters for the event, texture, subresource, and pixel.
        state: Daemon state with adapter and tex_map.

    Returns:
        Tuple of (response dict, keep_running bool).
    """
    for key in ("x", "y"):
        if key not in params:
            return _error_response(request_id, -32602, f"missing required param: {key}"), True

    x = int(params["x"])
    y = int(params["y"])

    try:
        eid, pipe = require_pipe(params, state, request_id)
    except PipeError as exc:
        return exc.response, True

    try:
        rt_rid, target_idx, sub, comp_type, _, selection_source = _resolve_texture_selection(
            params, state, pipe, x, y
        )
    except (PixelSelectionError, TypeError, ValueError) as error:
        code = error.code if isinstance(error, PixelSelectionError) else -32602
        return _error_response(request_id, code, str(error)), True

    controller = state.adapter.controller  # type: ignore[union-attr]
    pv = controller.PickPixel(rt_rid, x, y, sub, comp_type)

    fv = pv.floatValue
    return _result_response(
        request_id,
        {
            "x": x,
            "y": y,
            "eid": eid,
            "target": {"index": target_idx, "id": int(rt_rid)},
            "resource": {
                "id": int(rt_rid),
                "selection": selection_source,
                "targetIndex": target_idx,
            },
            "subresource": {"mip": sub.mip, "slice": sub.slice, "sample": sub.sample},
            "typeCast": _TYPE_CASTS[str(params.get("type_cast", "Typeless")).casefold()],
            "color": {"r": fv[0], "g": fv[1], "b": fv[2], "a": fv[3]},
        },
    ), True


HANDLERS: dict[str, Handler] = {
    "pixel_history": _handle_pixel_history,
    "pick_pixel": _handle_pick_pixel,
}
