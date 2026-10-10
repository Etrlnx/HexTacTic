"""Model evaluation CLI for Mimika."""

from __future__ import annotations

import argparse
import json
import sys

from .model_registry import DEFAULT_REGISTRY_DIR, ModelRegistry, ModelEvaluator


def main():
    parser = argparse.ArgumentParser(description="Evaluate Mimika models")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY_DIR), help="Model registry directory")
    parser.add_argument("--version", help="Model version to evaluate (default: current)")
    parser.add_argument("--vs-random", type=int, default=100, help="Games vs random player")
    parser.add_argument("--vs-version", help="Compare against another version")
    parser.add_argument("--games", type=int, default=100, help="Number of games for comparison")
    parser.add_argument("--device", default="cpu", help="Device to run on (cpu/cuda)")
    parser.add_argument("--output", help="Output JSON file for results")
    parser.add_argument("--list", action="store_true", help="List available model versions")

    args = parser.parse_args()

    registry = ModelRegistry(args.registry)

    if args.list:
        models = registry.list_models()
        if not models:
            print("No models registered.")
            return 0
        print(f"{'Version':<15} {'Registered':<20} {'Size':<10} {'Params':<12} {'Current'}")
        print("-" * 80)
        for m in models:
            current_marker = " *" if m["version"] == registry._index["current"] else ""
            print(f"{m['version']:<15} {m['registered_at'][:19]:<20} {m['file_size_bytes']:<10} {m['total_parameters']:<12} {current_marker}")
        return 0

    if not args.version and not args.vs_version:
        print("Error: --version required for evaluation")
        return 1

    evaluator = ModelEvaluator(registry)

    results = {}

    if args.vs_random > 0:
        version = args.version or registry._index["current"]
        print(f"Evaluating {version} vs Random ({args.vs_random} games)...")
        results["vs_random"] = evaluator.evaluate_vs_random(
            version=version, games=args.vs_random, device=args.device
        )
        r = results["vs_random"]
        print(f"  Win: {r['win_rate']:.2%} | Loss: {r['loss_rate']:.2%} | Draw: {r['draw_rate']:.2%}")

    if args.vs_version:
        version = args.version or registry._index["current"]
        print(f"Evaluating {version} vs {args.vs_version} ({args.games} games)...")
        results["vs_version"] = evaluator.evaluate_vs_previous(
            version=version, previous_version=args.vs_version, games=args.games, device=args.device
        )
        r = results["vs_version"]
        print(f"  {version} Win: {r.get(f'{version}_win_rate', 0):.2%} | "
              f"{args.vs_version} Win: {r.get(f'{args.vs_version}_win_rate', 0):.2%} | "
              f"Draw: {r['draw_rate']:.2%}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {args.output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())