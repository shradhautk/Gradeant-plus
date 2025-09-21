import json
import gradio as gr
import os
from pathlib import Path
import uuid

#############################################################################################################
proj_dir = Path(__file__).parent.parent  # as the file is in code directory
INPUT_FOLDER = proj_dir / "data" / "ga_format_input"
OUTPUT_FOLDER = proj_dir / "data" / "input"

# Ensure output folder exists
if not OUTPUT_FOLDER.exists():
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

print("Files available in 'ga_format_input' folder:")
if INPUT_FOLDER.exists():
    print(os.listdir(INPUT_FOLDER))
else:
    print("Input folder does not exist.")
#############################################################################################################

def has_key_recursive(data, key):
    """Recursively check if the key exists at any level in the JSON structure."""
    if isinstance(data, dict):
        if key in data:
            return True
        return any(has_key_recursive(value, key) for value in data.values())
    elif isinstance(data, list):
        return any(has_key_recursive(item, key) for item in data)
    return False

def find_subparts_recursive(data, subparts=None, parent_key=None):
    """Recursively find all dictionaries containing a 'subpart' key."""
    if subparts is None:
        subparts = []
    
    if isinstance(data, dict):
        if "subpart" in data:
            subparts.append(data)
        for key, value in data.items():
            find_subparts_recursive(value, subparts, key)
    elif isinstance(data, list):
        for item in data:
            find_subparts_recursive(item, subparts, parent_key)
    
    return subparts

def merge_json_files(hw_file, qp_file):
    # Check if files are uploaded
    if hw_file is None or qp_file is None:
        return "Error: Please upload both HW and QP files.", None, None

    try:
        # Load the HW and QP JSON files
        with open(hw_file.name, 'r', encoding='utf-8') as hw_file_handle:
            hw_data = json.load(hw_file_handle)

        with open(qp_file.name, 'r', encoding='utf-8') as qp_file_handle:
            qp_data = json.load(qp_file_handle)

        # Validate HW file for 'reply' key
        if not has_key_recursive(hw_data, "reply"):
            return "Error: HW file missing 'reply' key at any level.\nPlease re-upload the HW file.", None, None

        # Validate QP file for 'standard_answer' key
        if not has_key_recursive(qp_data, "standard_answer"):
            return "Error: QP file missing 'standard_answer' key at any level.\nPlease re-upload the QP file.", None, None

        # Initialize the merged JSON structure
        merged_data = {
            "homework": hw_data.get("homework", ""),
            "questions": []
        }

        # Process each question in HW
        hw_questions = hw_data.get("questions", [])
        qp_questions = qp_data.get("questions", [])
        
        if not hw_questions:
            return "Error: No questions found in HW file.", None, None
        if not qp_questions:
            return "Error: No questions found in QP file.", None, None

        for hw_question in hw_questions:
            question_number = hw_question.get("question_number")
            if not question_number:
                continue  # Skip if no question_number
            
            # Find matching QP question
            qp_question = next((q for q in qp_questions if q.get("question_number") == question_number), None)
            if not qp_question:
                print(f"Warning: No matching QP question found for question {question_number}")
                continue  # Skip if no matching QP question

            # Check if questions have subparts
            hw_has_subparts = "subparts" in hw_question and hw_question["subparts"]
            qp_has_subparts = "subparts" in qp_question and qp_question["subparts"]

            if hw_has_subparts and qp_has_subparts:
                # Handle questions with subparts
                hw_subparts = hw_question["subparts"]
                qp_subparts = qp_question["subparts"]
                processed_subparts = set()  # Track processed subparts to avoid duplicates
                
                for hw_subpart in hw_subparts:
                    subpart_letter = hw_subpart.get("subpart")
                    if not subpart_letter or subpart_letter in processed_subparts:
                        continue  # Skip if no subpart letter or already processed
                    
                    processed_subparts.add(subpart_letter)
                    
                    # Find matching QP subpart
                    qp_subpart = next((q for q in qp_subparts if q.get("subpart") == subpart_letter), None)
                    if not qp_subpart:
                        print(f"Warning: No matching QP subpart found for question {question_number}, subpart {subpart_letter}")
                        continue  # Skip if no matching QP subpart

                    # Create new question_number (e.g., 2a, 3b)
                    new_question_number = f"{question_number}{subpart_letter}"
                    
                    # Use the description from the subpart directly
                    full_description = hw_subpart.get("description", "")

                    # Ensure required fields exist
                    required_hw_fields = ["description", "reply"]
                    required_qp_fields = ["description", "standard_answer", "max_marks", "rubric"]
                    
                    missing_hw_fields = [field for field in required_hw_fields if field not in hw_subpart or not hw_subpart[field]]
                    missing_qp_fields = [field for field in required_qp_fields if field not in qp_subpart or not qp_subpart[field]]
                    
                    if missing_hw_fields or missing_qp_fields:
                        error_msg = f"Error: Missing required fields in Question {question_number} subpart {subpart_letter}."
                        if missing_hw_fields:
                            error_msg += f"\nMissing from HW: {', '.join(missing_hw_fields)}"
                        if missing_qp_fields:
                            error_msg += f"\nMissing from QP: {', '.join(missing_qp_fields)}"
                        error_msg += "\nPlease re-upload the file(s)."
                        return error_msg, None, None

                    question_entry = {
                        "question_id": f"q{new_question_number}",
                        "question_text": full_description,
                        "student_answer": hw_subpart["reply"],
                        "reference_answer": qp_subpart["standard_answer"],
                        "max_marks": qp_subpart["max_marks"],
                        "rubric": qp_subpart["rubric"]
                    }
                    merged_data["questions"].append(question_entry)
            else:
                # Handle questions without subparts
                required_hw_fields = ["description", "reply"]
                required_qp_fields = ["description", "max_marks", "standard_answer", "rubric"]
                
                missing_hw_fields = [field for field in required_hw_fields if field not in hw_question or not hw_question[field]]
                missing_qp_fields = [field for field in required_qp_fields if field not in qp_question or not qp_question[field]]
                
                if missing_hw_fields or missing_qp_fields:
                    error_msg = f"Error: Missing required fields in Question {question_number}."
                    if missing_hw_fields:
                        error_msg += f"\nMissing from HW: {', '.join(missing_hw_fields)}"
                    if missing_qp_fields:
                        error_msg += f"\nMissing from QP: {', '.join(missing_qp_fields)}"
                    error_msg += "\nPlease re-upload the file(s)."
                    return error_msg, None, None

                question_entry = {
                    "question_id": f"q{question_number}",
                    "question_text": hw_question["description"],
                    "student_answer": hw_question["reply"],
                    "reference_answer": qp_question["standard_answer"],
                    "max_marks": qp_question["max_marks"],
                    "rubric": qp_question["rubric"]
                }
                merged_data["questions"].append(question_entry)

        # Check if any questions were processed
        if not merged_data["questions"]:
            return "Error: No valid questions could be merged. Please check your input files.", None, None

        # Generate output filename
        output_filename = OUTPUT_FOLDER / f'{os.path.splitext(os.path.basename(hw_file.name))[0]}_with_QP.json'

        # Return success message, JSON content, and output filename
        success_msg = f"Successfully merged {len(merged_data['questions'])} questions.\nReady to save to: {output_filename}"
        return success_msg, json.dumps(merged_data, indent=2), str(output_filename)

    except FileNotFoundError as e:
        return f"Error: One or both files not found. Please check the uploaded files.\n{e}", None, None
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON format in one or both files.\n{e}", None, None
    except Exception as e:
        return f"Error: {str(e)}", None, None

def save_json_file(merged_json, output_filename):
    """Save the merged JSON data to the output folder."""
    try:
        # Ensure output folder exists
        if not OUTPUT_FOLDER.exists():
            OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        
        # Save the merged JSON to the output folder
        with open(output_filename, 'w', encoding='utf-8') as merged_file:
            # FIX: removed json.loads(), as Gradio passes a Python dict here
            json.dump(merged_json, merged_file, indent=2, ensure_ascii=False)
        
        return f"File successfully saved to: {output_filename}", output_filename
    except PermissionError as e:
        return f"Error: Permission denied when saving file. Check folder permissions.\n{e}", None
    except Exception as e:
        return f"Error: {str(e)}", None

# Create Gradio interface
with gr.Blocks(title="JSON File Merger") as demo:
    gr.Markdown("## Merge Homework and Question Paper JSON Files")
    gr.Markdown(
        f"""
        **Instructions:**
        - Upload Homework (HW) and Question Paper (QP) JSON files
        - HW file must contain 'reply' key at any level
        - QP file must contain 'standard_answer' key at any level
        - Subparts will be converted to main questions in the merged file
        - Files will be validated before merging
        - After merging, click 'Save to Output Folder' to save the merged file
        
        **File Locations:**
        - Input HW & QP files should be from: `{INPUT_FOLDER}`
        - Merged QA file will be saved to: `{OUTPUT_FOLDER}`
        """
    )
    
    with gr.Row():
        with gr.Column():
            hw_input = gr.File(label="Upload Homework JSON File", file_types=[".json"])
        with gr.Column():
            qp_input = gr.File(label="Upload Question Paper JSON File", file_types=[".json"])

    submit_button = gr.Button("Merge Files", variant="primary")
    
    with gr.Row():
        output_json = gr.JSON(label="Merged JSON Output")
    
    with gr.Row():
        output_message = gr.Textbox(label="Merge Status")
        output_filename_state = gr.State()
    
    with gr.Row():
        save_button = gr.Button("Save to Output Folder", variant="secondary")
    
    with gr.Row():
        download_file = gr.File(label="Download Merged JSON File")
        save_message = gr.Textbox(label="Save Status")
    
    submit_button.click(
        fn=merge_json_files,
        inputs=[hw_input, qp_input],
        outputs=[output_message, output_json, output_filename_state]
    )
    
    save_button.click(
        fn=save_json_file,
        inputs=[output_json, output_filename_state],
        outputs=[save_message, download_file]
    )

# Launch the Gradio interface
if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, share=False)