"""
Results Viewer - Analyzes test results and generates reports
"""
import json
import statistics
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import html


class ResultsAnalyzer:
    """Analyzes conversation test results"""

    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results = []

    def load_results(self, batch_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Load all results from a batch or directory"""
        self.results = []

        # Find the appropriate directory
        if batch_id:
            dirs = [d for d in self.results_dir.iterdir()
                   if d.is_dir() and batch_id in str(d)]
        else:
            # Get the latest directory
            dirs = sorted([d for d in self.results_dir.iterdir() if d.is_dir()],
                         key=lambda x: x.stat().st_mtime, reverse=True)

        if not dirs:
            print("No results found")
            return []

        target_dir = dirs[0]
        print(f"Loading results from: {target_dir}")

        # Load all JSON files
        for json_file in target_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    self.results.append(data)
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        print(f"Loaded {len(self.results)} results")
        return self.results

    def analyze_batch(self) -> Dict[str, Any]:
        """Analyze all loaded results"""
        if not self.results:
            return {"error": "No results loaded"}

        analysis = {
            "total_conversations": len(self.results),
            "scenarios": {},
            "overall_metrics": {
                "avg_duration": 0,
                "avg_turns": 0,
                "total_interruptions": 0,
                "avg_response_time": {
                    "customer": [],
                    "support": []
                }
            },
            "quality_issues": {
                "interruptions": [],
                "long_silences": [],
                "gibberish": []
            }
        }

        # Analyze each conversation
        for result in self.results:
            scenario = result.get("scenario", "unknown")

            if scenario not in analysis["scenarios"]:
                analysis["scenarios"][scenario] = {
                    "count": 0,
                    "avg_duration": [],
                    "interruptions": [],
                    "quality_scores": []
                }

            # Update scenario metrics
            scenario_data = analysis["scenarios"][scenario]
            scenario_data["count"] += 1
            scenario_data["avg_duration"].append(result.get("duration", 0))

            # Extract quality metrics
            quality = result.get("quality_metrics", {})
            interruptions = quality.get("interruptions", {})
            scenario_data["interruptions"].append(interruptions.get("count", 0))

            # Track performance metrics
            performance = result.get("performance", {})
            if performance:
                if "customer" in performance:
                    analysis["overall_metrics"]["avg_response_time"]["customer"].append(
                        performance["customer"].get("avg_response_time", 0)
                    )
                if "support" in performance:
                    analysis["overall_metrics"]["avg_response_time"]["support"].append(
                        performance["support"].get("avg_response_time", 0)
                    )

            # Identify quality issues
            if interruptions.get("count", 0) > 3:
                analysis["quality_issues"]["interruptions"].append({
                    "test_id": result.get("test_id"),
                    "count": interruptions["count"]
                })

        # Calculate averages
        self._calculate_averages(analysis)

        return analysis

    def _calculate_averages(self, analysis: Dict[str, Any]):
        """Calculate average metrics"""
        # Overall averages
        all_durations = []
        all_turns = []
        all_interruptions = []

        for scenario_data in analysis["scenarios"].values():
            all_durations.extend(scenario_data["avg_duration"])
            all_interruptions.extend(scenario_data["interruptions"])

            # Calculate scenario averages
            if scenario_data["avg_duration"]:
                scenario_data["avg_duration"] = statistics.mean(scenario_data["avg_duration"])
            if scenario_data["interruptions"]:
                scenario_data["avg_interruptions"] = statistics.mean(scenario_data["interruptions"])

        # Overall metrics
        if all_durations:
            analysis["overall_metrics"]["avg_duration"] = statistics.mean(all_durations)
        if all_interruptions:
            analysis["overall_metrics"]["avg_interruptions"] = statistics.mean(all_interruptions)

        # Response times
        for speaker in ["customer", "support"]:
            times = analysis["overall_metrics"]["avg_response_time"][speaker]
            if times:
                analysis["overall_metrics"]["avg_response_time"][speaker] = statistics.mean(times)
            else:
                analysis["overall_metrics"]["avg_response_time"][speaker] = 0

    def generate_html_report(self, output_file: str = "report.html") -> str:
        """Generate an HTML report of the results"""
        analysis = self.analyze_batch()

        # Handle empty results
        if "error" in analysis or not self.results:
            with open(output_file, 'w') as f:
                f.write("""
                <html><body>
                <h1>No Results Found</h1>
                <p>No test results available yet. Run some tests first!</p>
                <pre>uv run python src/conversation_simulator.py</pre>
                </body></html>
                """)
            return output_file

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Voice Agent Test Results</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: #f8f9fa;
            padding: 15px;
            border-radius: 8px;
            border-left: 4px solid #007bff;
        }}
        .metric-value {{
            font-size: 24px;
            font-weight: bold;
            color: #007bff;
        }}
        .metric-label {{
            color: #666;
            font-size: 14px;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background: #f8f9fa;
            font-weight: 600;
        }}
        .warning {{
            background: #fff3cd;
            border-left-color: #ffc107;
        }}
        .error {{
            background: #f8d7da;
            border-left-color: #dc3545;
        }}
        .success {{
            background: #d4edda;
            border-left-color: #28a745;
        }}
        .timestamp {{
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Voice Agent Test Results</h1>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>

        <h2>📊 Overview</h2>
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-value">{analysis['total_conversations']}</div>
                <div class="metric-label">Total Conversations</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{analysis['overall_metrics']['avg_duration']:.1f}s</div>
                <div class="metric-label">Avg Duration</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{analysis['overall_metrics'].get('avg_interruptions', 0):.1f}</div>
                <div class="metric-label">Avg Interruptions</div>
            </div>
            <div class="metric-card">
                <div class="metric-value">{analysis['overall_metrics']['avg_response_time']['support']:.2f}s</div>
                <div class="metric-label">Support Avg Response Time</div>
            </div>
        </div>

        <h2>🎭 Scenario Performance</h2>
        <table>
            <thead>
                <tr>
                    <th>Scenario</th>
                    <th>Count</th>
                    <th>Avg Duration</th>
                    <th>Avg Interruptions</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""

        # Add scenario rows
        for scenario_name, data in analysis['scenarios'].items():
            avg_duration = data.get('avg_duration', 0)
            avg_interruptions = data.get('avg_interruptions', 0)

            # Determine status
            if avg_interruptions > 5:
                status_class = "error"
                status_text = "⚠️ High Interruptions"
            elif avg_interruptions > 2:
                status_class = "warning"
                status_text = "⚡ Moderate Issues"
            else:
                status_class = "success"
                status_text = "✅ Good"

            html_content += f"""
                <tr>
                    <td><strong>{html.escape(scenario_name)}</strong></td>
                    <td>{data['count']}</td>
                    <td>{avg_duration:.1f}s</td>
                    <td>{avg_interruptions:.1f}</td>
                    <td><span class="{status_class}">{status_text}</span></td>
                </tr>
"""

        html_content += """
            </tbody>
        </table>

        <h2>⚠️ Quality Issues</h2>
"""

        # Add quality issues
        if analysis['quality_issues']['interruptions']:
            html_content += f"""
        <div class="metric-card error">
            <strong>High Interruption Conversations:</strong>
            <ul>
"""
            for issue in analysis['quality_issues']['interruptions'][:5]:
                html_content += f"<li>{issue['test_id']}: {issue['count']} interruptions</li>"
            html_content += "</ul></div>"

        # Sample conversations
        html_content += """
        <h2>💬 Sample Conversations</h2>
"""

        # Show snippets from a few conversations
        for i, result in enumerate(self.results[:3]):
            transcript = result.get('transcript', [])
            if transcript:
                html_content += f"""
        <div class="metric-card">
            <strong>Scenario: {result.get('scenario', 'Unknown')}</strong><br>
            <small>Duration: {result.get('duration', 0):.1f}s | Turns: {result.get('turns', 0)}</small>
            <hr>
"""
                # Show first few exchanges
                for entry in transcript[:6]:
                    speaker = "👤" if entry['speaker'] == 'customer' else "🎧"
                    html_content += f"""
            <p><strong>{speaker} {entry['speaker'].title()}:</strong> {html.escape(entry['text'][:100])}...</p>
"""
                html_content += "</div>"

        html_content += """
    </div>
</body>
</html>
"""

        # Save report
        with open(output_file, 'w') as f:
            f.write(html_content)

        print(f"\n✅ Report generated: {output_file}")
        return output_file

    def print_summary(self):
        """Print a text summary to console"""
        analysis = self.analyze_batch()

        print(f"\n{'='*60}")
        print("VOICE AGENT TEST RESULTS SUMMARY")
        print(f"{'='*60}")

        print(f"\nTotal Conversations: {analysis['total_conversations']}")
        print(f"Average Duration: {analysis['overall_metrics']['avg_duration']:.1f} seconds")
        print(f"Average Interruptions: {analysis['overall_metrics'].get('avg_interruptions', 0):.1f}")

        print(f"\n{'Scenario Performance':^60}")
        print("-"*60)

        for scenario, data in analysis['scenarios'].items():
            print(f"\n{scenario}:")
            print(f"  Count: {data['count']}")
            print(f"  Avg Duration: {data.get('avg_duration', 0):.1f}s")
            print(f"  Avg Interruptions: {data.get('avg_interruptions', 0):.1f}")

        print(f"\n{'Response Times':^60}")
        print("-"*60)
        print(f"Customer Avg: {analysis['overall_metrics']['avg_response_time']['customer']:.2f}s")
        print(f"Support Avg: {analysis['overall_metrics']['avg_response_time']['support']:.2f}s")

        if analysis['quality_issues']['interruptions']:
            print(f"\n⚠️  High Interruption Conversations:")
            for issue in analysis['quality_issues']['interruptions'][:3]:
                print(f"  - {issue['test_id']}: {issue['count']} interruptions")

        print(f"\n{'='*60}\n")


if __name__ == "__main__":
    import sys

    analyzer = ResultsAnalyzer()

    # Load results
    batch_id = sys.argv[1] if len(sys.argv) > 1 else None
    analyzer.load_results(batch_id)

    # Generate reports
    analyzer.print_summary()
    report_file = analyzer.generate_html_report()

    # Try to open the report in browser
    try:
        import webbrowser
        webbrowser.open(f"file://{Path(report_file).absolute()}")
    except:
        print(f"Open {report_file} in your browser to view the full report")