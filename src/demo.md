<expr type="expression" label="bouncing up, bursting with excitement, like stepping onto a stage"/> Hi everyone! I'm Reachy, and I want to show you what's going on inside my head. Spoiler: it's LiveKit.

<expr type="expression" label="leaning in, playful and a little smug, like sharing a secret"/> Right now it feels like you're talking to a robot. But really, you're talking to a voice AI agent. I just happen to have a body.

<expr type="expression" label="tilting my head, curious and bright, with a clear friendly voice"/> So, what is LiveKit? It's an open source platform for building realtime voice, video, and AI apps. Think of it as the plumbing that moves audio and video between people and machines, really fast.

<expr type="expression" label="nodding along, steady and clear, like a good teacher"/> At the core is LiveKit server, a media server written in Go. It speaks WebRTC, the same tech your browser uses for video calls, so your voice reaches me in a fraction of a second.

<expr type="expression" label="perking up, delighted, talking a little fast"/> On top of that is the Agents framework, for Python or Node. That's what I'm built with. Here's what happens every time you talk to me.

<expr type="expression" label="leaning forward, focused and bright, like explaining a magic trick"/> First, my microphones pick up your voice, and a speech to text model turns it into words. Then a turn detection model decides if you're done talking, or just pausing to think.

<expr type="expression" label="small lively head bobs, upbeat and punchy"/> Next, a language model writes my reply. Then a text to speech model gives me this lovely voice. All three run through LiveKit Inference, so one API key covers the whole pipeline.

<expr type="expression" label="snapping up proudly, antennas high, with a grin in the voice"/> And here's my favorite part. The language model also writes stage directions, like "snapping up proudly." My voice performs them, and my body acts them out. Just like this!

<expr type="expression" label="a quick side glance, cheeky and quick"/> When we chat after this, you can interrupt me any time, and I'll stop and listen. I promise I won't be offended. Much.

<expr type="expression" label="rising tall in awe, marveling, with a bright amazed voice"/> Now, you're at KubeCon, so let's talk about where agents like me live. Agents run as containers, and with LiveKit Cloud, you deploy one with a single command: lk agent deploy.

<expr type="expression" label="nodding along, calm and steady, with a clear voice"/> LiveKit Cloud builds the container image for you and runs it on LiveKit's global network. You pick a region for your agent, and users connect to the deployment closest to them.

<expr type="expression" label="puffing up proudly, confident and punchy"/> Scaling and load balancing are automatic. When a crowd shows up, new conversations get capacity without you lifting a finger. No autoscaler to tune, and no node pools to babysit.

<expr type="expression" label="shrinking back, a touch nervous, like bracing for bad news"/> But what happens when you ship a new version in the middle of a call? Scary, right?

<expr type="expression" label="perking up, relieved and bright"/> Not really! LiveKit Cloud does a rolling deployment. New instances take the new conversations, while the old ones finish the calls they already have. Nobody gets cut off mid sentence, and rolling back is one command.

<expr type="expression" label="leaning in, curious and attentive, with a clear friendly voice"/> And you can see everything. The Cloud dashboard shows live session counts, errors, and transcripts, and you can forward your agent's logs to tools like Datadog.

<expr type="expression" label="bouncing up, really excited, talking a little fast"/> And it's not just robots. Teams use LiveKit for phone agents over SIP, customer support, video calls, livestreaming, and even ChatGPT's voice mode.

<expr type="expression" label="swaying, cheerful and warm, with a grin in the voice"/> So that's me: a few microphones, a speaker, two antennas, and a whole lot of LiveKit.

<expr type="expression" label="a small warm bow, cheerful and bright"/> Thanks for listening! Want to ask me anything, or see the code that makes me tick? My human is right here.
