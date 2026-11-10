"""Windows entry point: desktop by default, legacy recorder commands on demand."""
import sys


def main():
    if len(sys.argv) == 1 or sys.argv[1] in {'--smoke-test', '--screenshot', '--version', '--connection-test'}:
        from desktop import main as desktop_main
        desktop_main()
    else:
        from recorder import main as recorder_main
        recorder_main()


if __name__ == '__main__':
    main()
