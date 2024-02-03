import pennylane as qml
import numpy as np
from kivy.lang import Builder
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.label import MDLabel
from kivy.clock import Clock
from concurrent.futures import ThreadPoolExecutor
import speedtest
import httpx
import asyncio
import subprocess

# Initialize the quantum device
dev = qml.device('default.qubit', wires=4)

# Define the quantum circuit to include jitter
@qml.qnode(dev)
def quantum_circuit(download_speed, upload_speed, ping, jitter):
    # Normalize the metrics for simplicity, including jitter
    r, g, b, j = download_speed / 100, upload_speed / 100, 1 - ping / 1000, jitter / 10
    qml.RY(np.pi * r, wires=0)
    qml.RY(np.pi * g, wires=1)
    qml.RY(np.pi * b, wires=2)
    qml.RY(np.pi * j, wires=3)  # Apply rotation for jitter
    qml.CNOT(wires=[0, 1])
    qml.CNOT(wires=[1, 2])
    qml.CNOT(wires=[2, 3])
    return qml.probs(wires=[0, 1, 2, 3])

# Function to perform the network test, measure jitter, and run the quantum circuit
def perform_network_test():
    st = speedtest.Speedtest()
    st.download()
    st.upload()
    ping = st.results.ping

    try:
        # Measure jitter using ping command
        process = subprocess.Popen(["ping", "-c", "10", "google.com"], stdout=subprocess.PIPE)
        output, _ = process.communicate()
        jitter = parse_jitter_from_ping_output(output)

        # Run the quantum circuit
        quantum_result = quantum_circuit(st.results.download / 1e6, st.results.upload / 1e6, ping, jitter)
        
    except subprocess.CalledProcessError as e:
        print("Error measuring jitter:", e)
        jitter = None  # Set jitter to None if measurement fails
        quantum_result = None  # Set quantum result to None if an error occurs

    return st.results.download / 1e6, st.results.upload / 1e6, ping, jitter, quantum_result

# Function to parse jitter from ping output (adjust for your system's output format)
def parse_jitter_from_ping_output(output):
    lines = output.decode().splitlines()
    for line in lines:
        if "mdev" in line:
            jitter_str = line.split("=")[1].strip()  # Example parsing
            jitter = float(jitter_str)  # Convert to float
            return jitter

    return None  # Return None if jitter info not found

# Async function to call GPT-4 for sentiment analysis, considering jitter and quantum result
async def analyze_sentiment(network_data, quantum_result):
    prompt = f"Network quality data: Download speed {network_data[0]:.2f} Mbps, Upload speed {network_data[1]:.2f} Mbps, Ping {network_data[2]} ms, Jitter {network_data[3]:.2f} ms. Quantum probabilities: {quantum_result}. Analyze the overall network sentiment."
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/engines/text-davinci-003/completions",
            headers={"Authorization": f"Bearer YOUR_OPENAI_API_KEY"},
            json={"prompt": prompt, "max_tokens": 60}
        )
        result = response.json()
        return result['choices'][0]['text'] if response.status_code == 200 else "Error in sentiment analysis"

class NetworkQualityApp(MDApp):
    def build(self):
        self.screen = MDScreen()
        
        self.test_button = MDRaisedButton(
            text="Test Network Quality",
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            on_release=self.on_test_network
        )
        
        self.result_label = MDLabel(
            text="Press the button to test network quality",
            halign="center",
            pos_hint={"center_x": 0.5, "center_y": 0.4}
        )
        
        self.screen.add_widget(self.test_button)
        self.screen.add_widget(self.result_label)
        
        return self.screen

    def on_test_network(self, instance):
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(perform_network_test)
        future.add_done_callback(lambda x: asyncio.run(self.perform_sentiment_analysis(x.result())))

    async def perform_sentiment_analysis(self, network_data):
        sentiment_result = await analyze_sentiment(network_data, network_data[-1])
        Clock.schedule_once(lambda dt: self.update_ui_with_sentiment(sentiment_result, network_data))

    def update_ui_with_sentiment(self, sentiment_result, network_data):
        # Update to display sentiment and network data including jitter and quantum result
        self.result_label.text = f"Network sentiment: {sentiment_result}\nDownload: {network_data[0]:.2f} Mbps\nUpload: {network_data[1]:.2f} Mbps\nPing: {network_data[2]} ms\nJitter: {network_data[3]:.2f} ms\nQuantum Result: {network_data[-1]}"
        

if __name__ == "__main__":
    NetworkQualityApp().run()
