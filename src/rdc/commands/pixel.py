"""rdc pixel command -- pixel history query."""

from __future__ import annotations

from typing import Any

import click

from rdc.commands._helpers import call, complete_eid
from rdc.commands.vfs import _fmt_pixel_mod
from rdc.formatters.json_fmt import write_json
from rdc.formatters.options import list_output_options, render_list


@click.command("pixel")
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
@list_output_options
def pixel_cmd(
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
    no_header: bool,
    use_jsonl: bool,
    quiet: bool,
) -> None:
    """Query pixel history at (X, Y) for the current or specified event."""
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

    result = call("pixel_history", params)

    if use_json:
        write_json(result)
        return

    modifications = result.get("modifications", [])

    def _table() -> None:
        if not no_header:
            click.echo("EID\tFRAG\tDEPTH\tPASSED\tFLAGS")
        for m in modifications:
            click.echo(_fmt_pixel_mod(m))

    render_list(
        modifications,
        use_json=False,
        use_jsonl=use_jsonl,
        quiet=quiet,
        quiet_key="eid",
        table=_table,
    )
