import argparse
import os
import subprocess
import traceback
from pathlib import Path

import yaml


def replace_context(recipe_str, new_context_line):
    """Replace context line in recipe_str."""
    variable, value = new_context_line.strip().split(": ")
    lines = recipe_str.splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{variable}:"):
            # Keep the leading whitespace
            whitespace = line[: line.index(f"{variable}:")]
            lines[i] = f"{whitespace}{new_context_line}"
            break
    return "\n".join(lines)


def run_copier_update(recipe_path, bump_build=False, copier_arg_list=None):
    """Run `copier update` to update recipe from template."""
    print(f"Updating recipe from template for: {recipe_path.parent}")

    run_args = [
        "copier",
        "update",
        str(recipe_path.parent),
    ]
    if copier_arg_list is not None:
        run_args.extend(copier_arg_list)

    subprocess.run(run_args, check=True, env=os.environ)

    if bump_build:
        with open(recipe_path) as f:
            recipe = yaml.safe_load(f)

        current_build = recipe["context"].get("build", None)

        if current_build is not None:
            orig_recipe_str = recipe_path.read_text()
            recipe_str = replace_context(
                orig_recipe_str,
                f'build: "{int(current_build) + 1}"',
            )
            # restore trailing newline if it was there before
            if orig_recipe_str.endswith("\n"):
                recipe_str += "\n"
            recipe_path.write_text(recipe_str)


def main():
    parser = argparse.ArgumentParser(
        epilog="Remaining arguments are passed to `copier update` (e.g. --defaults)."
    )
    parser.add_argument(
        "recipe_dir",
        nargs="?",
        default=Path("recipes"),
        type=Path,
    )
    parser.add_argument(
        "--bump-build",
        dest="bump_build",
        action="store_true",
    )
    args, extra_arg_list = parser.parse_known_args()

    recipe_dir = args.recipe_dir.resolve()

    for recipe_path in recipe_dir.glob("**/recipe.yaml"):
        if not (recipe_path.parent / ".copier-answers.yml").exists():
            continue
        try:
            run_copier_update(
                recipe_path,
                bump_build=args.bump_build,
                copier_arg_list=extra_arg_list,
            )
        except KeyboardInterrupt:
            break
        except Exception:
            tb = traceback.format_exc()
            print(f"Error updating {recipe_path.parent}: {tb}")


if __name__ == "__main__":
    main()
