import openai
import speech_recognition as sr
import os
import tkinter as tk
from tkinter import messagebox
from threading import Thread
import time
import json

# Function to load API key from env.txt
def load_api_key():
    try:
        with open("env.txt", "r") as file:
            for line in file:
                if line.startswith("OPENAI_API_KEY"):
                    return line.strip().split("=")[1]
    except FileNotFoundError:
        print("Error: env.txt file not found. Please create env.txt and add your API key.")
        return None

# Function to load questions from a mock file based on the given mock number
def load_mock_questions(mock_number):
    """Loads questions from a mock file based on the given mock number."""
    mock_filename = f"mock{mock_number}.json"
    mock_path = os.path.join("mocks", mock_filename)

    if not os.path.exists(mock_path):
        print(f"Error: {mock_path} not found!")
        return None

    with open(mock_path, "r", encoding="utf-8") as file:
        try:
            questions = json.load(file)
            print(f"Questions loaded successfully: {questions}")  # Debugging line
            return questions
        except json.JSONDecodeError:
            print(f"Error: Invalid JSON format in {mock_filename}")
            return None

# Initialize recognizer and microphone
recognizer = sr.Recognizer()
microphone = sr.Microphone()
recording = False  # Flag to track recording state
max_recording_time = 300  # 5 minutes (in seconds)
start_time = None

# Interview question bank and initial question index
questions = []
question_index = 0
scores = []  # Store the scores for each question

# Function to update the countdown timer
def update_timer(timer_label):
    while recording:
        elapsed = time.time() - start_time
        remaining = max(0, max_recording_time - int(elapsed))
        minutes, seconds = divmod(remaining, 60)
        timer_label.config(text=f"Time Remaining: {minutes:02}:{seconds:02}")
        if remaining == 0:
            toggle_recording(None)  # Auto-stop recording at 5 minutes
        time.sleep(1)

def toggle_recording(event=None):  # Set a default value for event
    global recording, start_time
    if not recording:
        recording = True
        start_time = time.time()
        status_label.config(text="Recording... Speak now!", fg="red")
        Thread(target=transcribe_speech).start()  # Run in background thread
        Thread(target=update_timer, args=(timer_label,)).start()  # Start countdown timer
    else:
        recording = False
        status_label.config(text="Processing...", fg="blue")


# Function to transcribe speech (records up to 5 minutes)
def transcribe_speech():
    global recording
    with microphone as source:
        recognizer.adjust_for_ambient_noise(source)  # Reduce background noise
        print("Listening... Speak now.")
        
        audio_data = []
        while recording and (time.time() - start_time < max_recording_time):
            try:
                audio = recognizer.listen(source, timeout=5)  # Capture chunks
                audio_data.append(audio)
            except sr.WaitTimeoutError:
                continue  # Continue listening if no speech detected
        
        # Stop recording if no audio was captured
        if not audio_data:
            status_label.config(text="No speech detected.", fg="red")
            return

        print("Processing speech...")
        try:
            full_audio = sr.AudioData(
                b"".join(a.frame_data for a in audio_data),
                audio_data[0].sample_rate,
                audio_data[0].sample_width,
            )
            response_text = recognizer.recognize_google(full_audio)  # Use Google Speech-to-Text
            print("Transcribed Text:", response_text)
            status_label.config(text="Evaluating response...", fg="blue")
            evaluate_response(response_text)  # Call evaluation function
        except sr.UnknownValueError:
            status_label.config(text="Could not understand speech.", fg="red")
        except sr.RequestError:
            status_label.config(text="Speech recognition service unavailable.", fg="red")

# Function to evaluate response
def evaluate_response(response_text):
    global question_index
    # Ensure that the correct question is selected based on the question_index
    question = questions[question_index - 1]  # -1 because question_index starts at 1

    if not question:
        print("No question found for evaluation.")
        return

    print(f"Evaluating Question: {question['question']}")  # Debugging line

    # Load the mark scheme specific to the current question
    mark_scheme = f"""
    **Good Points (each adds +1 to score)**
    {', '.join(question['mark_scheme']['good_points'])}

    **Red Flags (each deducts -2 from score)**
    {', '.join(question['mark_scheme']['red_flags'])}

    **Scoring System**
    - If no good points are mentioned, the candidate scores **0/10** and is told they did not properly answer the question.
    - If the prompt seems to have been roughly answered, the candidate gets **4/10 minimum.**
    - Each additional good point adds **+1 mark.**
    - Each red flag deducts **-2 marks.**
    - If the answer is under a 90 seconds then tell the candidate that they were too brief.
    - Red flags are clearly explained as damaging to an interview.
    - Red flags will cap the answer at 3.
    - Final score is capped between **0 and 10.**
    """

    # Construct the prompt with the correct question and mark scheme
    prompt = f"""
    You are an AI trained to score UK medical school spoken interview transcriptions.

    Question: {question['question']}
    Candidate's response: {response_text}

    Mark scheme:
    {mark_scheme}

    Please evaluate the response based on the provided mark scheme and give a score out of 10 along with reasoning. Do not explain the scoring system to the user or mention the addition of points. Just give the score and the feedback.
    """

    api_key = load_api_key()
    if not api_key:
        return

    client = openai.OpenAI(api_key=api_key)

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an AI trained to score UK medical school interview responses."},
                {"role": "user", "content": prompt}
            ]
        )
        evaluation = response.choices[0].message.content.strip()
        print("\nEvaluation:\n", evaluation)  # Debugging line
        score = extract_score(evaluation)
        scores.append(score)  # Store the score
        show_feedback_popup(evaluation)  # Show feedback in popup window

        # Enable the "Next Question" button after evaluation is complete
        next_button.config(state="normal")
        status_label.config(text="Evaluation complete. You can proceed to the next question.", fg="green")

    except openai.OpenAIError as e:
        print(f"Error: {str(e)}")
        status_label.config(text="API Error. Check terminal.", fg="red")
        # Disable "Next Question" button in case of error
        next_button.config(state="disabled")


# Function to extract the score from the AI feedback
def extract_score(feedback):
    # Parse the score from the feedback
    lines = feedback.split("\n")
    for line in lines:
        if "Score" in line:
            try:
                score = int(line.split(":")[1].strip())
                return score
            except ValueError:
                continue
    return 0  # Default to 0 if score is not found

# Function to show the feedback in a new popup window
def show_feedback_popup(feedback_text):
    feedback_window = tk.Toplevel(root)
    feedback_window.title("Feedback")

    # Create a frame for the feedback (to control scrolling)
    feedback_frame = tk.Frame(feedback_window)
    feedback_frame.pack(padx=20, pady=20)

    # Create a label for the feedback with bullet points formatting
    formatted_feedback = format_feedback(feedback_text)
    feedback_label = tk.Label(
        feedback_frame,
        text=formatted_feedback,
        font=("Arial", 14),
        fg="white",
        justify="left",
        wraplength=500,  # Adjusted to make text wrap appropriately
        padx=20,
        pady=10
    )
    feedback_label.pack()

    # Create a button to close the feedback window
    close_button = tk.Button(
        feedback_window,
        text="Close",
        command=feedback_window.destroy,
        font=("Arial", 14),
        fg="black",
        bg="lightgray"
    )
    close_button.pack(pady=10)

# Function to format the feedback with bullet points
def format_feedback(feedback_text):
    feedback_lines = feedback_text.split('\n')
    formatted_feedback = ""
    for line in feedback_lines:
        if line.strip():
            formatted_feedback += f"- {line.strip()}\n"
    return formatted_feedback

# GUI Setup for Mock Selection
def select_mock_gui():
    """Allows the user to select which mock to work with."""
    select_root = tk.Tk()
    select_root.title("Select a Mock")

    def on_mock_selected():
        mock_number = int(mock_choice.get())
        select_root.destroy()
        start_mock(mock_number)

    # Label and dropdown to choose mock number
    label = tk.Label(select_root, text="Select Mock Number:", font=("Arial", 18))
    label.pack(pady=20)

    # List available mocks in ascending order
    mock_files = [f for f in os.listdir("mocks") if f.startswith("mock") and f.endswith(".json")]
    mock_numbers = sorted([int(f[4:-5]) for f in mock_files])  # Extract mock numbers and sort in ascending order

    mock_choice = tk.StringVar(select_root)
    mock_choice.set(str(mock_numbers[0]))  # Default to the lowest mock number

    dropdown = tk.OptionMenu(select_root, mock_choice, *map(str, mock_numbers))
    dropdown.pack(pady=10)

    # Button to proceed after selection
    proceed_button = tk.Button(select_root, text="Start Mock", command=on_mock_selected)
    proceed_button.pack(pady=20)

    select_root.mainloop()

# Function to start mock
def start_mock(mock_number=1):
    global questions
    print(f"Loading mock {mock_number}...")  # Debugging line
    questions = load_mock_questions(mock_number)
    
    if questions:  # Check if questions list is populated
        print(f"Questions: {questions}")  # Debugging line
        setup_interview_gui(mock_number)
    else:
        print("Error: No questions loaded.")

# Function to set up the interview GUI to display questions one at a time
def setup_interview_gui(mock_number):
    global question_index
    question_index = 1

    # Initialize Tkinter window
    global root
    root = tk.Tk()
    root.title(f"Medical School Mock Interview - Mock {mock_number}")

    # Create the label for the interview question
    global question_label
    question_label = tk.Label(root, text=questions[0]['question'], font=("Arial", 18), wraplength=500)
    question_label.pack(pady=20)

    # Create the status label (for recording status)
    global status_label
    status_label = tk.Label(root, text="Press Start to begin.", font=("Arial", 14))
    status_label.pack(pady=10)

    # Create a countdown timer
    global timer_label
    timer_label = tk.Label(root, text="Time Remaining: 05:00", font=("Arial", 14))
    timer_label.pack(pady=10)

    # Button to start/stop recording
    start_button = tk.Button(root, text="Start/Stop Recording", command=toggle_recording, font=("Arial", 14))
    start_button.pack(pady=20)

    # Disable "Next Question" button initially and create the button
    global next_button
    next_button = tk.Button(root, text="Next Question", command=next_question, font=("Arial", 14), state="disabled")
    next_button.pack(pady=10)

    # Back to mock selection button
    back_button = tk.Button(root, text="Back To Main Menu", command=lambda: back_to_mock_selection(), font=("Arial", 14))
    back_button.pack(pady=20)

    # Start the interview window
    root.mainloop()

# Function to load and display the next question
def next_question():
    global question_index, question_label
    if question_index < len(questions):
        question_index += 1
        # Update the question label to the next question
        question_label.config(text=questions[question_index - 1]['question'])
        # Reset the status label for each new question
        status_label.config(text="Press Start to begin.", fg="black")
        timer_label.config(text="Time Remaining: 05:00")
    else:
        status_label.config(text="You have completed all questions.", fg="green")
        print("All questions completed.")

# Function to handle returning to mock selection
def back_to_mock_selection():
    root.destroy()
    select_mock_gui()  # Reopen mock selection window

# Start mock selection
select_mock_gui()