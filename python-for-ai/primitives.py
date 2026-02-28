from helpers import calculate_average

print("Hello world!")
print("I'm learning AI with Python")


# Im a comment
"""
Im a multiline comment
"""


name = "John"
fullName = name + " Doe" 
age = 25
fString = f"My name is {name} and I am {age} years old"
print(name, fullName, fString, age)
print(fullName.lower())
print(fullName.upper())
print(fullName.capitalize())
print(fullName.strip())
print(fullName.split())
print(len(fullName))
print(fullName.startswith("John"))
print(fullName.endswith("Doe"))
print(fullName.find("John"))


integer = 10
float = 10.5
square = integer ** 2
print(integer, float, square)
print(calculate_average([1, 2, 3, 4, 5]))


