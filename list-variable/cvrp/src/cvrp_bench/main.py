import vrplib

from cvrp_bench.domain.models import Instance, Solution


def main():
    # Read VRPLIB formatted instances (default)
    instance = vrplib.read_instance("data/X/X-n101-k25.vrp")
    solution = vrplib.read_solution("data/X/X-n101-k25.sol")
    instance = Instance.model_validate(instance)
    solution = Solution.model_validate(solution)
    print(instance)
    print(solution)


if __name__ == "__main__":
    main()
