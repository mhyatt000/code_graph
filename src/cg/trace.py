import sys
from rich import print
import os
import argparse

# Add lgrey to path so we can import it
sys.path.insert(0, os.path.dirname(__file__))

from lgrey.main import main

history = set() # list

from pathlib import Path

d = Path(__file__).parent

def trace_calls(frame, event, arg):
  if event == 'call':
      code = frame.f_code
      if 'lgrey' in code.co_filename:
          f = Path(code.co_filename)
          # get local filename from d as root
          f = f.relative_to(d)

          # Get calling function info
          caller_frame = frame.f_back
          caller_func = caller_frame.f_code.co_name if caller_frame else None
          caller_class = None

          if caller_frame:
              # Check if caller is a method (has 'self' or 'cls')
              if 'self' in caller_frame.f_locals:
                  caller_class = caller_frame.f_locals['self'].__class__.__name__
              elif 'cls' in caller_frame.f_locals:
                  caller_class = caller_frame.f_locals['cls'].__name__

          payload = {
              "filename": str(f),
              "function": code.co_name,
              "lineno": frame.f_lineno,
              "args": frame.f_locals,
              "event": event,
              "called_from": caller_func,
              "called_from_class": caller_class,
          }
          # history.append(payload)
          history.add((payload['filename'], payload['function'], payload['lineno'], caller_func, caller_class))

  return trace_calls

# Set tracer
sys.settrace(trace_calls)

# Run actual training/usage by directly calling main with args
sys.argv = ['trace.py', '-i', 'lgrey']
main()

sys.settrace(None)

# Now history contains everything actually executed
print("\nFunctions actually called during execution:")
print(len(history), "calls recorded.\n")
for filename, funcname, lineno, caller_func, caller_class in history:
    caller_str = f"{caller_class}.{caller_func}" if caller_class else None
    print(f"{filename}:{lineno} | {funcname} - {caller_str}")


print(len(set([f[1] for f in history])), "unique functions called.\n")
print(len(set([f[0] for f in history])), "unique files called.\n")
# clases
print(len(set([f[4] for f in history if f[4] is not None])), "unique classes called.\n")
print(set([f[4] for f in history if f[4] is not None]))
