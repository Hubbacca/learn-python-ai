names = ["John", "Jane", "Jim", "Jill"]
for name in names:
    print(name)

names.append("Derulo")
print(names)
names.remove("Derulo")
print(names)
names.pop()
print(names)
names.clear()
print(names)


person = {
    "name": "John",
    "age": 20,
    "city": "New York"
}
print(person)
print(person["name"])
print(person.get("name"))

person["name"] = "Jane"
print(person)
print(person.keys())
print(person.values())
print(person.items())


# Tuples like list but immutable
personTuple = ("John", 20, "New York")
print(personTuple)
print(personTuple[0])
print(personTuple.index("New York"))


# Sets like list but unordered and unique
personSet = {"John", 20, "New York"}
personSet = set(["John", 20, "New York", "New York"])
print(personSet)
personSet.add("Los Angeles")
print(personSet)
personSet.remove("Los Angeles")
print(personSet)
personSet.clear()
print(personSet)