"""
helpers lib
"""

import subprocess
import threading

def format_time(seconds):
    if seconds < 60:
        return f"{seconds:.3f}s"

    minutes = int(seconds // 60)
    remaining_seconds = seconds % 60
    return f"{minutes:02d}:{remaining_seconds:06.3f}"


def run_cmd(cmd):
    print(f'COMMAND: {cmd}')

    def reader_thread(pipe, process):
        for line in iter(pipe.readline, b''):
            if line:
                print(f'{line.decode().strip()}')
            if process.poll() is not None:
                break

    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as proc:

        stdout_thread = threading.Thread(target=reader_thread, args=(proc.stdout, proc))
        stderr_thread = threading.Thread(target=reader_thread, args=(proc.stderr, proc))

        stdout_thread.start()
        stderr_thread.start()

        proc.wait()
        return_code = proc.returncode

        stdout_thread.join()
        stderr_thread.join()

        if return_code != 0:
            print(f"Failed with return code: {return_code}")
