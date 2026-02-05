# Voice Agent Testing Framework

## 🎯 Overview

A comprehensive testing framework for voice AI agents that simulates customer-support conversations. This system allows you to:

- **Simulate both sides** of customer support conversations
- **Test multiple scenarios** (angry customers, confused users, technical issues, etc.)
- **Capture rich metrics** beyond just transcripts (interruptions, latency, speech quality)
- **Generate detailed reports** with actionable insights
- **Run tests in parallel** for rapid iteration

## 🚀 Quick Start

### Prerequisites

1. Set up your environment variables in `.env.local`:
```bash
LIVEKIT_API_KEY=your_key
LIVEKIT_API_SECRET=your_secret
LIVEKIT_URL=wss://your-livekit-url
OPENAI_API_KEY=your_openai_key  # Or other LLM provider
```

2. Install dependencies (if not already installed):
```bash
uv sync
```

3. Download model files:
```bash
uv run python src/agent.py download-files
```

### Running Tests

#### Interactive Mode (Easiest)
```bash
python run_test.py
```

This opens an interactive menu where you can:
- Run single scenarios
- Run all scenarios
- View results
- Generate reports

#### Command Line Mode
```bash
# Run a specific scenario
python run_test.py test angry_refund

# Run all scenarios
python run_test.py test all

# View latest results
python run_test.py results

# Generate HTML report
python run_test.py report
```

## 📚 Available Test Scenarios

### 1. **Angry Refund** (`angry_refund`)
- **Customer**: Karen Smith
- **Personality**: Aggressive, impatient, easily frustrated
- **Goal**: Get immediate refund for broken product
- **Difficulty**: Very difficult
- **Special behaviors**: Interrupts often, demands manager, threatens bad reviews

### 2. **Confused Elderly** (`confused_elderly`)
- **Customer**: Harold Johnson
- **Personality**: Confused but polite, needs repetition
- **Goal**: Reset password and access account
- **Difficulty**: Moderate
- **Special behaviors**: Goes off-topic, asks for clarification, confused by technical terms

### 3. **Technical Bug Report** (`technical_bug_report`)
- **Customer**: Alex Chen
- **Personality**: Technical, precise, impatient with non-technical responses
- **Goal**: Get bug acknowledged and fix timeline
- **Difficulty**: Moderate
- **Special behaviors**: Challenges vague responses, asks for escalation to engineering

### 4. **Friendly Billing** (`friendly_billing`)
- **Customer**: Sarah Williams
- **Personality**: Friendly, understanding, patient
- **Goal**: Get duplicate charge refunded
- **Difficulty**: Easy
- **Special behaviors**: Thanks agent, makes small talk, appreciates good service

### 5. **Edge Case Nightmare** (`edge_case_nightmare`)
- **Customer**: Jordan Mitchell
- **Personality**: Persistent, detail-oriented, tracks everything
- **Goal**: Resolve multiple interrelated issues
- **Difficulty**: Very difficult
- **Special behaviors**: Brings up new issues, asks for ticket numbers, tests agent thoroughly

## 🏗️ Architecture

```
┌─────────────────┐         ┌─────────────────┐
│ Customer Agent  │◄────────►│  Support Agent  │
│   (Synthetic)   │ WebRTC  │   (Mock Acme)   │
└────────┬────────┘         └────────┬────────┘
         │                           │
         └───────────┬───────────────┘
                     │
              ┌──────▼──────┐
              │  LiveKit    │
              │    Room     │
              └──────┬──────┘
                     │
           ┌─────────▼─────────┐
           │ Metrics Collector │
           └─────────┬─────────┘
                     │
              ┌──────▼──────┐
              │   Results   │
              │   Analyzer  │
              └─────────────┘
```

## 📊 Metrics Captured

### Conversation Metrics
- **Duration**: Total conversation length
- **Turns**: Number of speaker exchanges
- **Speaking ratio**: Customer vs support talking time
- **Response times**: Average time to respond

### Quality Metrics
- **Interruptions**: Who interrupted whom and when
- **Silence gaps**: Long pauses in conversation
- **Gibberish detection**: Low-confidence speech segments
- **Speech rate**: Words per minute for each speaker

### Performance Metrics
- **First response time**: Time to first support response
- **Resolution time**: Time to resolve issue
- **Task completion**: Whether goal was achieved
- **Sentiment progression**: How customer emotion changed

## 📁 Project Structure

```
livekit-starter/
├── src/
│   ├── customer_agent.py       # Synthetic customer personas
│   ├── support_agent.py        # Mock support agent (uses Acme prompt)
│   ├── conversation_orchestrator.py  # Connects agents in rooms
│   ├── test_runner.py          # Batch test execution
│   ├── metrics_collector.py    # Captures conversation metrics
│   └── results_viewer.py       # Analyzes and reports results
├── prompts/
│   └── acme_system_prompt.txt  # Support agent instructions
├── results/
│   └── [timestamp]/            # Test results by batch
│       ├── test_*.json         # Individual conversations
│       └── batch_summary.json  # Aggregate metrics
├── run_test.py                 # Main entry point
└── TEST_FRAMEWORK.md           # This file
```

## 🔧 Customization

### Adding New Customer Scenarios

Edit `src/customer_agent.py` and add to `SCENARIO_TEMPLATES`:

```python
"new_scenario": {
    "customer_name": "John Doe",
    "issue": "Specific problem description",
    "goal": "What they want to achieve",
    "personality": "How they behave",
    "difficulty": "easy|moderate|difficult|very difficult",
    "special_behavior": "Unique behaviors",
    # ... other fields
}
```

### Customizing Support Agent

Replace the content in `prompts/acme_system_prompt.txt` with your actual support agent prompt.

### Adjusting Metrics Thresholds

Edit `src/metrics_collector.py`:

```python
self.silence_threshold = 3.0  # Seconds to count as silence gap
self.gibberish_confidence_threshold = 0.5  # STT confidence threshold
self.overlap_threshold = 0.5  # Seconds to count as interruption
```

## 🚀 Advanced Usage

### Running Parallel Tests

```python
# In test_runner.py
batch = TestBatch("my-batch")
for scenario in scenarios:
    batch.add_test(scenario)

# Run 10 conversations simultaneously
results = await batch.run(parallel=10)
```

### Connecting to Real Agents (Future)

The framework is designed to easily connect to real agents via:
- **WebRTC**: Direct room connection
- **SIP/Twilio**: Phone integration
- **API**: REST endpoints

## 📈 Viewing Results

### Console Summary
```bash
python run_test.py results
```

Shows:
- Total conversations run
- Average metrics per scenario
- Quality issues detected
- Response time analysis

### HTML Report
```bash
python run_test.py report
```

Generates an interactive HTML report with:
- Visual metrics dashboard
- Scenario performance breakdown
- Quality issue highlighting
- Sample conversation snippets

## 🐛 Troubleshooting

### Agents Not Connecting
- Check LiveKit credentials in `.env.local`
- Verify LiveKit server is running
- Check network connectivity

### Low Quality Scores
- Adjust VAD sensitivity
- Check microphone settings
- Review STT provider settings

### Tests Timing Out
- Increase timeout in `test_runner.py`
- Check for infinite conversation loops
- Verify agent termination conditions

## 🎯 Next Steps

1. **Add your real prompts** to `prompts/acme_system_prompt.txt`
2. **Create custom scenarios** matching your use cases
3. **Run batch tests** to establish baselines
4. **Iterate on prompts** based on metrics
5. **Connect to production agents** when ready

## 📝 Notes

- This framework simulates both sides locally for maximum control
- Designed to later connect to real agents via Twilio/SIP
- All metrics are captured in real-time during conversations
- Results are saved as JSON for integration with other tools

---

Built for rapid voice agent testing and optimization. Perfect for prompt engineering and quality assurance.