class BaseCalculator:
    def __init__(self, name):
        self.name = name
    
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def multiply(self, a, b):
        return a * b

    def divide(self, a, b):
        return a / b

class ScientificCalculator(BaseCalculator):
    def __init__(self, name):
        super().__init__(name)

    def add_cells(self, a, b):
        result = super().add(a, b)
        return f"You have {result} cells"

base_calculator = BaseCalculator(name="Base Calculator")
calculator = ScientificCalculator(name="Scientific Calculator")

print(base_calculator.add(1, 2))
print(calculator.add_cells(1, 2))