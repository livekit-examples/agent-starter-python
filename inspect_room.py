from livekit import rtc
import inspect

print("Room.local_participant type:")
# We can't easily instantiate a Room without connecting, but we can inspect the class if we know it.
# rtc.Room.local_participant is a property returning LocalParticipant.

print("\nLocalParticipant.publish_data signature:")
print(inspect.signature(rtc.LocalParticipant.publish_data))
