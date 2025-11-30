from livekit.agents import inference
import inspect

print("LLM class signature:")
print(inspect.signature(inference.LLM.__init__))

print("\nLLM methods:")
for name, method in inspect.getmembers(inference.LLM, predicate=inspect.isfunction):
    print(f"{name}: {inspect.signature(method)}")
