"""Force the pinned ComfyUI checkout into CPU mode during CI probes."""

from comfy.cli_args import args

args.cpu = True
