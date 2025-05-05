print('hello world')
import subprocess

def bad_func(user_input):
    subprocess.call(user_input, shell=True)
