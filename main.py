#!/usr/bin/env python3
"""
Text-to-Video Pipeline: Converts user text into a narrated video presentation
using Gemini for storyboarding and Manim for visualization with gTTS narration.
"""

import os
import json
import subprocess
import sys
from dotenv import load_dotenv
import google.generativeai as genai

# Load environment variables
load_dotenv(".env.local")

# At the top of the file, after imports
with open("manim_context.txt") as f:
    manim_context = f.read()

with open("manim_voiceover_context.txt") as f:
    manim_voiceover_context = f.read()

complete_context = f"""
Manim Voiceover Context:
{manim_voiceover_context}

Manim Context:
{manim_context}
"""

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env.local file")

genai.configure(api_key=GEMINI_API_KEY)

def flash(prompt, user_input=None):
    """
    Use Gemini Flash to generate content based on a prompt.
    
    Args:
        prompt: The prompt to send to Gemini
        user_input: Optional user input to include in the prompt
    
    Returns:
        The generated content from Gemini
    """
    model = genai.GenerativeModel('gemini-2.5-flash-preview-05-20')
    
    if user_input:
        full_prompt = f"{prompt}\n\nUser text: {user_input}"
    else:
        full_prompt = prompt
    
    response = model.generate_content(full_prompt)
    return response.text

def run_command(command):
    """
    Run a shell command and return whether it was successful and any error output.
    
    Args:
        command: List containing the command and its arguments
    
    Returns:
        Tuple of (success_bool, error_message)
    """
    try:
        result = subprocess.run(
            command, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, e.stderr

def parse_json_from_text(text):
    """
    Extract JSON from text that might contain markdown formatting.
    
    Args:
        text: Text potentially containing JSON with markdown formatting
    
    Returns:
        Parsed JSON object
    """
    # Try to find JSON between triple backticks
    import re
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
    
    if json_match:
        json_str = json_match.group(1)
    else:
        # If no markdown format, assume the whole text is JSON
        json_str = text
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to clean up the string if it's not valid JSON
        # Sometimes models add extra text or formatting
        lines = json_str.split('\n')
        cleaned_lines = []
        json_started = False
        
        for line in lines:
            if line.strip().startswith('{') or line.strip().startswith('['):
                json_started = True
            
            if json_started:
                cleaned_lines.append(line)
                
                if (line.strip().endswith('}') or line.strip().endswith(']')) and not any(c in line for c in ',":\''):
                    break
        
        try:
            return json.loads('\n'.join(cleaned_lines))
        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON: {e}")
            print(f"Original text: {text}")
            raise

def main():
    """Main function to run the text-to-video pipeline."""
    if len(sys.argv) < 2:
        print("Usage: python main.py 'Your text for the lesson'")
        sys.exit(1)
    
    user_text = sys.argv[1]
    print(f"Generating storyboard for: {user_text}")
    
    # Step 1: Generate storyboard with Gemini Flash
    storyboard_prompt = """
    Split the user text into ≤5 slides.
    Return JSON items with:
      narration  (≤40 words)
      visual_spec (one-line)

    Important: Make sure you do not have any backticks, backquotes in your narration.
    
    The output should be valid JSON with a structure like:
    {
      "slides": [
        {
          "narration": "Text for narration",
          "visual_spec": "Description of what to show visually"
        },
        ...
      ]
    }
    Visual_spec should be something possible by the manim library. Do not make it too complex.
    Important: Make sure you do not have any backticks in your narration.
    """
    
    storyboard_text = flash(storyboard_prompt, user_text)
    storyboard = parse_json_from_text(storyboard_text)
    print(storyboard)
    
    print(f"Generated storyboard with {len(storyboard['slides'])} slides")
    
    # Step 3: Generate and render each slide
    for i, slide in enumerate(storyboard["slides"]):
        print(f"\nProcessing slide {i+1}/{len(storyboard['slides'])}")
        
        # Generate Manim code for the slide
        code_prompt = f"""
Create **one** Manim scene class named **Slide{i}** that follows ALL of the rules
below.  Return *only* valid Python for that class—no comments, prints, or extra
text around it.

1 Imports & global config 
from manim import *
from manim_voiceover import VoiceoverScene
from manim_voiceover.services.gtts import GTTSService

config.pixel_width  = 640
config.pixel_height = 480
config.frame_rate   = 24

# fixed colour palette – use only these names
apple_color  = "#FF0000"
stem_color   = "#8B4513"
leaf_color   = "#00FF00"
ground_color = "#888888"
arrow_color  = "#FFFF00"
text_color   = "#FFFFFF"

2 Class skeleton
class Slide{i}(VoiceoverScene):
    def construct(self):
        self.set_speech_service(GTTSService())

        with self.voiceover(text=\"\"\"{slide['narration']}\"\"\") as tracker:
            #### IMPLEMENT THE VISUAL BELOW THIS LINE ####
            #  use only tracker.duration for timing
            #  rate_func=linear    (all lowercase)
            #  never call self.wait(), wait_until, remaining_duration, etc.
            #  never call .fade_out() – use FadeOut(obj) instead
            #  never pass mobject=… into FadeOut/FadeIn
            #  never use MathTex / Tex.  Use Text() for any formula.
            #  never use AnimationGroup with an empty list.
            #  no 3-D, no tables/graphs/surfaces/plots.

            {slide['visual_spec']}
            # every self.play() must include run_time=tracker.duration
            # or a fraction of it, e.g. run_time=tracker.duration*0.5

RULES SUMMARY
• **NO** FRAME_WIDTH, FRAME_HEIGHT, config.*, self.camera.frame.
  If you must span the stage: Line(LEFT*7, RIGHT*7).to_edge(DOWN, buff=0.5)
• **NO** built-in Manim colours (BLUE, GREEN_C, …) – only the six hex vars.
• **NO** MathTex/Tex ⇒ avoids the LaTeX tool-chain crash.
• All fades must be FadeIn(obj) / FadeOut(obj)  (not obj.fade_out()).
• Every AnimationGroup must contain at least ONE mobject.
• Only keyword args that exist in Manim 0.19.
"""
        
        code = flash(code_prompt)
        
        # Extract code from markdown if needed
        import re
        code_match = re.search(r'```python\s*([\s\S]*?)\s*```', code)
        if code_match:
            code = code_match.group(1)
        

        # Save the code to a file
        path = f"slide_{i:02}.py"
        with open(path, "w") as f:
            f.write(code)
        
        # Try to render the slide, with up to 3 attempts
        success = False
        for attempt in range(3):
            print(f"  Attempt {attempt+1}/3 to render slide {i+1}")
            ok, err = run_command(["manim", "-pql", path, f"Slide{i}"])
            
            if ok:
                success = True
                print(f"  Slide {i+1} rendered successfully")
                break
            else:
                print(f"  Error rendering slide {i+1}: {err}")
                
                # Try to fix the code with Gemini
                fix_prompt = f"""
                Rewrite the entire manim code for this slide {slide['visual_spec']} to fix the error. Error:\n{err}\n\nCode:\n{code}"
                Make the animation simpler and just give the code, no extra comments required.
                {code_prompt}
                """
                fixed_code = flash(fix_prompt)
                
                # Extract fixed code
                code_match = re.search(r'```python\s*([\s\S]*?)\s*```', fixed_code)
                if code_match:
                    fixed_code = code_match.group(1)
                
                # Save the fixed code
                with open(path, "w") as f:
                    f.write(fixed_code)
                
                code = fixed_code
        
        if not success:
            print(f"Failed to render slide {i+1} after 3 attempts")
            raise RuntimeError(f"Slide {i} failed 3×")
    
    # Step 4: Concatenate the videos if multiple slides were rendered
    if len(storyboard["slides"]) > 1:
        print("\nConcatenating videos...")
        
        # Create a list file for ffmpeg
        with open("list.txt", "w") as f:
            for i in range(len(storyboard["slides"])):
                f.write(f"file 'media/videos/slide_{i:02}/480p24/Slide{i}.mp4'\n")
        
        # Run ffmpeg to concatenate the videos
        ok, err = run_command([
            "ffmpeg", "-f", "concat", "-safe", "0", 
            "-i", "list.txt", "-c", "copy", "final_lesson.mp4"
        ])
        
        if ok:
            print("Videos concatenated successfully. Output: final_lesson.mp4")
        else:
            print(f"Error concatenating videos: {err}")
    else:
        # If there's only one slide, just copy it to the final output
        if len(storyboard["slides"]) == 1:
            ok, err = run_command([
                "cp", "media/videos/slide_00/480p24/Slide0.mp4", "final_lesson.mp4"
            ])
            
            if ok:
                print("Single video copied to final_lesson.mp4")
            else:
                print(f"Error copying video: {err}")
    
    print("\nPipeline completed successfully!")

if __name__ == "__main__":
    main()
