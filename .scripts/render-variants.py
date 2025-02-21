import argparse
import collections
import json
import os
import shutil
import sys
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml

def collapse_variant_matrix(variants):
    unique_keys = set()
    unique_keys.update(*tuple(set(v.keys()) for v in variants))

    combined_variant = collections.defaultdict(list)
    for variant in variants:
        # ignore noarch variants because they don't arise from the variant config
        if variant["target_platform"] == "noarch":
            continue
        for key in unique_keys:
            combined_variant[key].append(variant.get(key, ""))

    collapsed_variant = {}
    zip_keys = []
    for key, val in combined_variant.items():
        s = set(val)
        s.discard("")
        if len(s) == 0:
            # key not actually needed, probably from noarch variant
            continue
        elif len(s) == 1:
            collapsed_variant[key] = s.pop()
        else:
            collapsed_variant[key] = tuple(val)
            zip_keys.append(key)

    if len(zip_keys) > 1:
        collapsed_variant["zip_keys"] = zip_keys

    return collapsed_variant

def combine_platform_variants(platform_variants):
    unique_keys = set()
    unique_keys.update(*tuple(set(v.keys()) for v in platform_variants.values()))

    num_platforms = len(platform_variants)

    combined_variant = {}
    for key in unique_keys:
        platform_vals = {}
        for platform, variant in platform_variants.items():
            if key in variant:
                platform_vals[platform] = variant[key]
        unique_vals = set(platform_vals.values())
        if len(platform_vals) == num_platforms and len(unique_vals) == 1:
            # all platforms have the same value, so use that
            combined_variant[key] = unique_vals.pop()
        else:
            # platforms have different values, or some platforms don't have the key
            selector_vals = []
            for k, value in platform_vals.items():
                selector_vals.append({
                    "if": f"target_platform == '{k}'",
                    "then": value,
                })
            combined_variant[key] = selector_vals

    return combined_variant

def render_variants(recipe_path, target_platforms):
    """Render variants for recipe from conda-forge-pinning and local file."""
    base_run_args = [
        "rattler-build",
        "build",
        "--experimental",
        "--render-only",
        "--recipe",
        str(recipe_path),
        "--ignore-recipe-variants",
        "--variant-config",
        str(Path(os.environ["CONDA_PREFIX"]) / "conda_build_config.yaml"),
    ]
    global_variants = recipe_path.parent.parent / "variants.yaml"
    if global_variants.exists():
        base_run_args.extend([
            "--variant-config",
            str(global_variants),
        ])
    recipe_variants = recipe_path.parent / "recipe_variants.yaml"
    if recipe_variants.exists():
        base_run_args.extend([
            "--variant-config",
            str(recipe_variants),
        ])
    platform_variants = {}
    for target_platform in target_platforms:
        run_args = base_run_args + [
            # don't want build platform to change depending on where this
            # script is run, so just set it to match target platform
            "--build-platform",
            target_platform,
            "--target-platform",
            target_platform,
        ]
        with tempfile.NamedTemporaryFile(mode="w+", encoding="utf-8") as outfile:
            subprocess.run(run_args, check=True, stdout=outfile, env=os.environ)
            outfile.seek(0)
            content = outfile.read()
            metadatas = json.loads(content)
        if not isinstance(metadatas, list):
            metadatas = [metadatas]
        variants = [m["build_configuration"]["variant"] for m in metadatas]
        platform_variants[target_platform] = collapse_variant_matrix(variants)

    combined_variant = combine_platform_variants(platform_variants)
    variant_path = recipe_path.parent / "variants.yaml"
    if variant_path.exists():
        variant_path.unlink()
    # remove special variant keys that are not read from the config file
    del combined_variant["build_platform"]
    del combined_variant["target_platform"]
    variant_path.write_text(yaml.safe_dump(combined_variant))

    #variants_dir = recipe_path.parent / ".variants"
    #if variants_dir.exists():
        #for varfile in variants_dir.glob("*.yaml"):
            #varfile.unlink()
    #else:
        #variants_dir.mkdir()

    #for target_platform, variant in platform_variants.items():
        #variant_path = variants_dir / f"{target_platform}.yaml"
        ## remove special variant keys that are not read from the config file
        #del variant["build_platform"]
        #del variant["target_platform"]
        #variant_path.write_text(yaml.safe_dump(variant))

    print(f"Rendered variants for: {recipe_path}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "recipe_dir",
        nargs="?",
        default=Path("recipes"),
        type=Path,
    )
    parser.add_argument(
        "--manifest-path",
        dest="manifest_path",
        default=None,
        type=Path,
    )
    args = parser.parse_args()

    recipe_dir = args.recipe_dir.resolve()

    if args.manifest_path is None:
        for parent in (recipe_dir / "foo").parents:
            manifest_path = parent / "pixi.toml"
            if manifest_path.exists():
                break
        else:
            print("Cannot find pixi.toml manifest file! Specify --manifest-path")
    else:
        manifest_path = args.manifest_path.resolve()

    with open(manifest_path, "rb") as f:
        manifest = tomllib.load(f)

    target_platforms = manifest["project"]["platforms"]

    for recipe_path in recipe_dir.glob('**/recipe.yaml'):
        try:
            render_variants(recipe_path, target_platforms)
        except Exception as e:
            print(f"Error processing {recipe_path}: {e}")
            raise e

if __name__ == '__main__':
    main()
