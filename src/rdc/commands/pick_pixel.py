"""rdc pick-pixel command -- single-pixel color readback."""

from __future__ import annotations

from typing import Any

import click

from rdc.commands._helpers import call, complete_eid
from rdc.formatters.json_fmt import write_json


@click.command("pick-pixel")
@click.argument("x", type=int)
@click.argument("y", type=int)
@click.argument("eid", required=False, type=int, shell_complete=complete_eid)
@click.option("--target", type=int, help="Color target index (default 0)")
@click.option("--resource-id", type=int, help="Texture resource id instead of an output target")
@click.option("--mip", default=0, type=int, help="Mip level (default 0)")
@click.option("--slice", "array_slice", default=0, type=int, help="Array/depth slice (default 0)")
@click.option("--sample", default=0, type=int, help="MSAA sample index (default 0)")
@click.option(
    "--type-cast",
    type=click.Choice(
        [
            "Typeless",
            "Float",
            "UNorm",
            "SNorm",
            "UInt",
            "SInt",
            "UScaled",
            "SScaled",
            "Depth",
            "UNormSRGB",
        ],
        case_sensitive=False,
    ),
    default="Typeless",
    show_default=True,
    help="RenderDoc component interpretation",
)
@click.option("--json", "use_json", is_flag=True, help="JSON output")
def pick_pixel_cmd(
    x: int,
    y: int,
    eid: int | None,
    target: int | None,
    resource_id: int | None,
    mip: int,
    array_slice: int,
    sample: int,
    type_cast: str,
    use_json: bool,
) -> None:
    """Read pixel color at (X, Y) from a texture at an event."""
    if target is not None and resource_id is not None:
        raise click.UsageError("--target and --resource-id are mutually exclusive")

    params: dict[str, Any] = {
        "x": x,
        "y": y,
        "mip": mip,
        "slice": array_slice,
        "sample": sample,
        "type_cast": type_cast,
    }
    if resource_id is not None:
        params["resource_id"] = resource_id
    else:
        params["target"] = 0 if target is None else target
    if eid is not None:
        params["eid"] = eid
    result = call("pick_pixel", params)
    if use_json:
        write_json(result)
        return
    c = result["color"]
    click.echo(f"r={c['r']:.4f}  g={c['g']:.4f}  b={c['b']:.4f}  a={c['a']:.4f}")
