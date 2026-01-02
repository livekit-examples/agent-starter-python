from livekit.agents import JobProcess, WorkerOptions
from livekit.plugins import silero


class AgentServer:
    def __init__(self):
        self._entrypoint = None
        self._prewarm = None
        self._agent_name = None

    def rtc_session(self, agent_name: str = None):
        def decorator(func):
            self._entrypoint = func
            self._agent_name = agent_name
            return func

        return decorator

    @property
    def setup_fnc(self):
        return self._prewarm

    @setup_fnc.setter
    def setup_fnc(self, func):
        self._prewarm = func

    def __call__(self):
        return WorkerOptions(
            entrypoint_fnc=self._entrypoint,
            prewarm_fnc=self._prewarm,
            agent_name=self._agent_name,
        )


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
