from livekit.agents import Agent, AgentSession
import inspect

print("Agent __init__ signature:")
print(inspect.signature(Agent.__init__))

print("\nAgentSession __init__ signature:")
print(inspect.signature(AgentSession.__init__))

print("\nAgentSession.start signature:")
print(inspect.signature(AgentSession.start))
