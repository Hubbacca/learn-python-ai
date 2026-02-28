try:
    result = "hello" + 5
    print(result)
except TypeError:
    print("Type error: cannot concatenate str and int")
finally:
    print("This will always execute")

print("Program continues...")