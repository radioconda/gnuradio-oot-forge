import argparse
import collections
import json
import os
import subprocess
import tempfile
import tomllib
from pathlib import Path

import yaml


def collapse_variant_matrix(variants):
    unique_keys = set()
    unique_keys.update(*tuple(set(v.keys()) for v in variants))
    # remove special variant keys that are not read from the config file
    unique_keys.discard("build_platform")
    unique_keys.discard("target_platform")
    for key in unique_keys.copy():
        if key.startswith("__"):
            unique_keys.discard(key)

    # find values common to all variants
    common_keys = unique_keys.copy()
    common_values = {}
    for variant in variants:
        for key, val in variant.items():
            if key not in common_keys:
                continue
            if key not in common_values:
                common_values[key] = val
            elif common_values[key] != val:
                common_keys.discard(key)
                common_values.pop(key)

    # convert variant dictionaries to sets of (key, value) tuples
    # and reduce the variants by combining those that are subsets/supersets
    common_variant_set = set((k, v) for k, v in common_values.items())
    variant_sets = []
    for variant in variants:
        variant_set = common_variant_set.copy()
        for key, val in variant.items():
            if key not in unique_keys:
                continue
            variant_set.add((key, val))

        # join with existing variants when subset/superset otherwise add to list
        for existing_variant_set in variant_sets:
            if variant_set.issubset(existing_variant_set):
                break
            elif variant_set.issuperset(existing_variant_set):
                existing_variant_set.update(variant_set)
                break
        else:
            variant_sets.append(variant_set)

    # get the keys for unique values and the values unique to each variant
    zip_keys = set()
    unique_variants = []
    for variant_set in variant_sets:
        unique_variant_set = variant_set - common_variant_set
        unique_variant = collections.defaultdict(lambda: "")
        for k, v in unique_variant_set:
            zip_keys.add(k)
            unique_variant[k] = v
        unique_variants.append(unique_variant)

    # collapse into a single dict with tuple values for the unique keys
    collapsed_variant = common_values.copy()
    for key in zip_keys:
        collapsed_variant[key] = tuple(uv[key] for uv in unique_variants)

    if len(zip_keys) > 1:
        collapsed_variant["zip_keys"] = tuple(zip_keys)

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
                selector_vals.append(
                    {
                        "if": f"target_platform == '{k}'",
                        "then": value,
                    }
                )
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
        base_run_args.extend(
            [
                "--variant-config",
                str(global_variants),
            ]
        )
    recipe_variants = recipe_path.parent / "recipe_variants.yaml"
    if recipe_variants.exists():
        base_run_args.extend(
            [
                "--variant-config",
                str(recipe_variants),
            ]
        )
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
        if variants:
            platform_variants[target_platform] = collapse_variant_matrix(variants)

    combined_variant = combine_platform_variants(platform_variants)
    variant_path = recipe_path.parent / "variants.yaml"
    if variant_path.exists():
        variant_path.unlink()
    variant_path.write_text(yaml.safe_dump(combined_variant))

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

    for recipe_path in recipe_dir.glob("**/recipe.yaml"):
        try:
            render_variants(recipe_path, target_platforms)
        except Exception as e:
            print(f"Error processing {recipe_path}: {e}")


if __name__ == "__main__":
    main()
