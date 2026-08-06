"""Fetch and print an option chain for RELIANCE."""

from quantmind.derivatives import get_option_chain


def main():
    chain = get_option_chain("RELIANCE")
    print(f"Found {len(chain)} option contracts")
    for c in chain[:5]:
        print(c.name)


if __name__ == "__main__":
    main()
