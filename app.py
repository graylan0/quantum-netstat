import asyncio
import aiosqlite
import httpx
import pennylane as qml
import numpy as np
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.clock import Clock
import concurrent.futures
import json
import re
import speedtest

# Load configuration settings
with open('config.json', 'r') as config_file:
    config = json.load(config_file)

# Initialize the quantum device from config
dev = qml.device(config["quantum_device"], wires=config["quantum_wires"])

def quantum_circuit(download_speed, upload_speed, ping, jitter, normalization_factors):
    @qml.qnode(dev)
    def circuit():
        qml.RY(np.pi * (download_speed / normalization_factors['download_speed']), wires=0)
        qml.RY(np.pi * (upload_speed / normalization_factors['upload_speed']), wires=1)
        qml.RY(np.pi * (1 - ping / normalization_factors['ping']), wires=2)
        qml.RY(np.pi * (jitter / normalization_factors['jitter']), wires=3)
        qml.CNOT(wires=[0, 1])
        qml.CNOT(wires=[1, 2])
        qml.CNOT(wires=[2, 3])
        return qml.probs(wires=[0, 1, 2, 3])
    return circuit()

async def create_db():
    try:
        async with aiosqlite.connect(config["database_path"]) as db:
            await db.execute('''CREATE TABLE IF NOT EXISTS network_tests (
                                    id INTEGER PRIMARY KEY,
                                    download_speed REAL,
                                    upload_speed REAL,
                                    ping REAL,
                                    jitter REAL,
                                    quantum_result TEXT)''')
            await db.commit()
    except Exception as e:
        print(f"Error creating database: {e}")

async def insert_network_test(download_speed, upload_speed, ping, jitter, quantum_result):
    try:
        async with aiosqlite.connect(config["database_path"]) as db:
            await db.execute('''INSERT INTO network_tests (download_speed, upload_speed, ping, jitter, quantum_result)
                                    VALUES (?, ?, ?, ?, ?)''',
                             (download_speed, upload_speed, ping, jitter, str(quantum_result)))
            await db.commit()
    except Exception as e:
        print(f"Error inserting network test: {e}")

async def fetch_all_tests():
    try:
        async with aiosqlite.connect(config["database_path"]) as db:
            async with db.execute("SELECT * FROM network_tests") as cursor:
                return await cursor.fetchall()
    except Exception as e:
        print(f"Error fetching tests: {e}")
        return []

async def query_gpt4_for_normalization_factors():
    try:
        prompt = """
        Given a range of download speeds from 0 to 1000 Mbps, upload speeds from 0 to 500 Mbps, 
        ping from 0 to 100 ms, and jitter from 0 to 25 ms, 
        how should I normalize these values for analysis in a quantum computing model? 
        Please provide normalization factors for each metric.
        """
        
        headers = {"Authorization": f"Bearer {config['openai_api_key']}"}
        data = {
            "model": "text-davinci-003",
            "prompt": prompt,
            "max_tokens": 100
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.openai.com/v1/completions", headers=headers, json=data)
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['text']
            else:
                return "Error in analysis."
    except Exception as e:
        print(f"Error querying GPT-4: {e}")
        return "Error in analysis."

def parse_normalization_response(response):
    try:
        factors = ['download_speed', 'upload_speed', 'ping', 'jitter']
        normalization_factors = {}
        for factor in factors:
            match = re.search(f"{factor}: (\d+)", response)
            if match:
                normalization_factors[factor] = int(match.group(1))
            else:
                normalization_factors[factor] = 100  # Default value if not found
        return normalization_factors
    except Exception as e:
        print(f"Error parsing normalization response: {e}")
        return {factor: 100 for factor in factors}

class MyApp(App):
    def build(self):
        self.layout = BoxLayout(orientation='vertical')
        self.label = Label(text='Network Quality Analyzer')
        self.test_button = Button(text='Run Real Network Test')
        self.result_label = Label(text='Test results will appear here.')

        self.test_button.bind(on_press=lambda instance: asyncio.ensure_future(self.run_real_network_test()))

        self.layout.add_widget(self.label)
        self.layout.add_widget(self.test_button)
        self.layout.add_widget(self.result_label)

        return self.layout

    async def run_real_network_test(self):
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            st = await loop.run_in_executor(pool, speedtest.Speedtest)
            await loop.run_in_executor(pool, st.get_best_server)
            download_speed = await loop.run_in_executor(pool, st.download) / 1e6  # Convert to Mbps
            upload_speed = await loop.run_in_executor(pool, st.upload) / 1e6  # Convert to Mbps
            ping = st.results.ping
            jitter = st.results.jitter

        normalization_response = await query_gpt4_for_normalization_factors()
        normalization_factors = parse_normalization_response(normalization_response)

        quantum_result = quantum_circuit(download_speed, upload_speed, ping, jitter, normalization_factors)
        await insert_network_test(download_speed, upload_speed, ping, jitter, quantum_result)
        Clock.schedule_once(lambda dt: self.update_ui(download_speed, upload_speed, ping, jitter, quantum_result), 0)

    def update_ui(self, download_speed, upload_speed, ping, jitter, quantum_result):
        self.result_label.text = f'Real Test: Download {download_speed:.2f} Mbps, Upload {upload_speed:.2f} Mbps, Ping {ping} ms, Jitter {jitter} ms\nQuantum Result: {quantum_result}'

if __name__ == '__main__':
    asyncio.run(create_db())
    MyApp().run()
