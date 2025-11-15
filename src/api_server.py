"""
Simple API server for triggering voice conversations with web UI
"""
import asyncio
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
import os
from datetime import datetime
import traceback
from dotenv import load_dotenv

# Load environment variables
load_dotenv("../.env.local")

# Import our conversation simulator
from conversation_simulator import (
    ConversationSimulator,
    SCENARIOS,
    simulate_conversation
)

app = Flask(__name__, static_folder='web')
CORS(app)

# Ensure conversations directory exists
Path("conversations").mkdir(exist_ok=True)

@app.route('/')
def index():
    """Serve the main HTML page"""
    return send_from_directory('web', 'index.html')

@app.route('/api/scenarios')
def get_scenarios():
    """Get available scenarios with descriptions"""

    # Better scenario names for UI display
    scenario_names = {
        'cooperative_parent': '😊 Cooperative Parent - Easy Resolution',
        'angry_insufficient_funds': '😤 Angry Parent - Financial Stress',
        'wrong_person_family': '👩 Wrong Person - Wife Takes Message',
        'confused_elderly_hindi': '👴 Confused Elderly - Hindi Speaker',
        'financial_hardship': '😟 Financial Hardship - Needs Help',
        'already_paid_confusion': '🤔 Payment Confusion - Claims Paid',
        'payment_cancellation_attempt': '❌ Wants to Cancel - Needs Convincing',
        'call_back_later': '⏰ Busy Professional - Call Later'
    }

    scenarios_list = []
    for key, scenario in SCENARIOS.items():
        scenarios_list.append({
            'id': key,
            'display_name': scenario_names.get(key, key),
            'customer_name': scenario.get('customer_name', 'Unknown'),
            'difficulty': scenario.get('difficulty', 'medium'),
            'emotional_state': scenario.get('emotional_state', 'neutral'),
            'description': scenario.get('issue', 'No description'),
            'personality': scenario.get('personality', ''),
            'special_behavior': scenario.get('special_behavior', '')
        })
    return jsonify(scenarios_list)

@app.route('/api/generate', methods=['POST'])
def generate_conversation():
    """Generate a conversation with specified parameters"""
    try:
        data = request.json

        # Extract parameters
        scenario_id = data.get('scenario', 'cooperative_parent')
        tts_engine = data.get('tts_engine', 'auto')  # 'openai', 'elevenlabs', 'auto'
        max_turns = data.get('max_turns', 6)

        # OpenAI parameters (separated by speaker)
        openai_model = data.get('openai_model', 'tts-1')
        openai_voice_support = data.get('openai_voice_support', 'onyx')
        openai_voice_customer = data.get('openai_voice_customer', 'echo')
        openai_speed_support = data.get('openai_speed_support', 1.0)
        openai_speed_customer = data.get('openai_speed_customer', 1.0)

        # ElevenLabs parameters (separated by speaker)
        # Support agent settings
        elevenlabs_stability_support = data.get('elevenlabs_stability_support', 0.55)
        elevenlabs_similarity_support = data.get('elevenlabs_similarity_support', 0.75)
        elevenlabs_style_support = data.get('elevenlabs_style_support', 0.15)
        elevenlabs_speaker_boost_support = data.get('elevenlabs_speaker_boost_support', True)
        elevenlabs_speed_support = data.get('elevenlabs_speed_support', 0.98)

        # Customer settings
        elevenlabs_stability_customer = data.get('elevenlabs_stability_customer', 0.5)
        elevenlabs_similarity_customer = data.get('elevenlabs_similarity_customer', 0.75)
        elevenlabs_style_customer = data.get('elevenlabs_style_customer', 0.2)
        elevenlabs_speaker_boost_customer = data.get('elevenlabs_speaker_boost_customer', False)
        elevenlabs_speed_customer = data.get('elevenlabs_speed_customer', 1.0)

        # Get scenario
        scenario = SCENARIOS.get(scenario_id, SCENARIOS['cooperative_parent'])
        scenario = scenario.copy()
        scenario['name'] = scenario_id

        # Load support prompt
        prompt_file = Path("prompts/support_agent_system_prompt.txt")
        if prompt_file.exists():
            support_prompt = prompt_file.read_text()
        else:
            support_prompt = "You are a helpful customer support agent."

        # Determine TTS preference
        use_elevenlabs = None
        if tts_engine == 'elevenlabs':
            use_elevenlabs = True
        elif tts_engine == 'openai':
            use_elevenlabs = False
        # else 'auto' - let the simulator decide

        # Create custom simulator with parameters
        simulator = ConversationSimulator(scenario, support_prompt, use_elevenlabs=use_elevenlabs)

        # Store custom parameters for the simulator to use (separated by speaker)
        simulator.custom_params = {
            'openai': {
                'model': openai_model,
                'voice_support': openai_voice_support,
                'voice_customer': openai_voice_customer,
                'speed_support': float(openai_speed_support),
                'speed_customer': float(openai_speed_customer)
            },
            'elevenlabs': {
                'support': {
                    'stability': float(elevenlabs_stability_support),
                    'similarity_boost': float(elevenlabs_similarity_support),
                    'style': float(elevenlabs_style_support),
                    'use_speaker_boost': elevenlabs_speaker_boost_support,
                    'speed': float(elevenlabs_speed_support)
                },
                'customer': {
                    'stability': float(elevenlabs_stability_customer),
                    'similarity_boost': float(elevenlabs_similarity_customer),
                    'style': float(elevenlabs_style_customer),
                    'use_speaker_boost': elevenlabs_speaker_boost_customer,
                    'speed': float(elevenlabs_speed_customer)
                }
            }
        }

        # Generate conversation asynchronously
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Generate the conversation
        result = loop.run_until_complete(
            simulator.generate_conversation(max_turns=int(max_turns))
        )

        # Export files
        files = loop.run_until_complete(simulator.export_conversation())

        # Prepare response
        response = {
            'success': True,
            'scenario': scenario_id,
            'turns': result['metrics']['total_turns'],
            'transcript_file': files['transcript_file'],
            'audio_file': files['audio_file'],
            'tts_engine': 'ElevenLabs' if simulator.use_elevenlabs else 'OpenAI',
            'transcript': result['transcript']
        }

        return jsonify(response)

    except Exception as e:
        print(f"Error generating conversation: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/audio/<path:filename>')
def serve_audio(filename):
    """Serve generated audio files"""
    audio_path = Path('conversations') / filename
    if audio_path.exists():
        def generate():
            with open(audio_path, 'rb') as f:
                data = f.read(1024)
                while data:
                    yield data
                    data = f.read(1024)

        return Response(generate(), mimetype="audio/mpeg")
    else:
        return jsonify({'error': 'Audio file not found'}), 404

@app.route('/api/conversations')
def list_conversations():
    """List recent conversations"""
    conversations = []
    conv_dir = Path('conversations')

    # Get all mp3 files
    for audio_file in sorted(conv_dir.glob('*.mp3'), reverse=True)[:10]:
        # Find matching transcript
        base_name = audio_file.stem.replace('_conversation', '')
        transcript_file = conv_dir / f"{base_name}_transcript.json"

        conv_info = {
            'audio_file': audio_file.name,
            'timestamp': audio_file.stat().st_mtime,
            'size_kb': audio_file.stat().st_size // 1024,
            'scenario': 'unknown'
        }

        if transcript_file.exists():
            try:
                with open(transcript_file) as f:
                    data = json.load(f)
                    conv_info['scenario'] = data.get('scenario', {}).get('name', 'unknown')
                    conv_info['turns'] = data.get('metrics', {}).get('total_turns', 0)
            except:
                pass

        conversations.append(conv_info)

    return jsonify(conversations)

if __name__ == '__main__':
    print("Starting API server on http://localhost:5001")
    print("Open http://localhost:5001 in your browser to access the UI")
    app.run(debug=True, port=5001)