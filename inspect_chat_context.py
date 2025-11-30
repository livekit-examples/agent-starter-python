from livekit.agents import llm
import inspect

print("ChatContext init signature:")
print(inspect.signature(llm.ChatContext.__init__))

print("\nChatContext methods:")
for name, method in inspect.getmembers(llm.ChatContext, predicate=inspect.isfunction):
    print(f"{name}: {inspect.signature(method)}")

print("\nChatContext properties:")
for name, prop in inspect.getmembers(llm.ChatContext, predicate=lambda x: isinstance(x, property)):
    print(name)
