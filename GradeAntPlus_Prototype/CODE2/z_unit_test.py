#!/usr/bin/env python3
"""
Nuclear Physics Test Suite for GradeAnt+ Application
Tests the system with real nuclear physics questions
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys
import os
from datetime import datetime

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Define datetime_uuid locally
def datetime_uuid(seed: str):
    """Generate a datetime-based unique identifier with seed"""
    return f"{datetime.now().strftime('%Y%m%d_%H%M')}_{seed}"

try:
    from main import grade_ant_plus_main
    from utils import load_and_validate_questions
except ImportError as e:
    print(f"Warning: Could not import main modules: {e}")
    print("Make sure you're running this from the correct directory")

class NuclearPhysicsTestRunner:
    """Test runner specifically for nuclear physics questions"""
    
    def __init__(self):
        self.test_results = []
        self.test_data_dir = Path(tempfile.mkdtemp(prefix="gradeant_nuclear_"))
        self.setup_test_environment()
        self.create_nuclear_physics_questions()
    
    def setup_test_environment(self):
        """Create test directories"""
        (self.test_data_dir / "input").mkdir(parents=True)
        (self.test_data_dir / "output").mkdir(parents=True)
        print(f"Nuclear Physics test environment: {self.test_data_dir}")
    
    def create_nuclear_physics_questions(self):
        """Create nuclear physics test questions with varied correctness levels"""
        
        # Mix of correct, partially correct, and incorrect answers
        self.nuclear_questions = [
            {
                "question_id": "nuclear_001_correct",
                "question_text": "Calculate the binding energy of a deuteron (²H) given that its mass is 2.014102 u, the mass of a proton is 1.007276 u, and the mass of a neutron is 1.008665 u. Express your answer in MeV.",
                "student_answer": "Mass defect = (1.007276 + 1.008665) - 2.014102 = 0.001839 u. Using E = mc², binding energy = 0.001839 × 931.5 MeV/u = 1.71 MeV",
                "reference_answer": "Mass defect Δm = (mp + mn) - md = (1.007276 + 1.008665) - 2.014102 = 0.001839 u. Binding energy BE = Δm × 931.5 MeV/u = 0.001839 × 931.5 = 1.71 MeV"
            },
            {
                "question_id": "nuclear_002_needs_feedback",
                "question_text": "A sample contains 10¹⁵ radioactive nuclei with a half-life of 8 days. How many nuclei will remain after 24 days?",
                "student_answer": "After 24 days, I need to use the exponential decay formula. N = N₀ × e^(-λt). But I'm not sure how to find λ from the half-life. Let me try: λ = 1/8 days, so N = 10¹⁵ × e^(-24/8) = 10¹⁵ × e^(-3) ≈ 4.98 × 10¹³",
                "reference_answer": "Number of half-lives n = t/t₁/₂ = 24/8 = 3. Using N = N₀(1/2)ⁿ, N = 10¹⁵ × (1/2)³ = 10¹⁵/8 = 1.25 × 10¹⁴ nuclei"
            },
            {
                "question_id": "nuclear_003_misconception",
                "question_text": "What happens to the atomic number and mass number in beta-minus decay?",
                "student_answer": "In beta-minus decay, an electron is emitted from the nucleus. Since we're losing a negatively charged particle, the atomic number decreases by 1, but the mass number stays the same because electrons have negligible mass.",
                "reference_answer": "In β⁻ decay: n → p + e⁻ + ν̄ₑ. Mass number A remains constant, atomic number Z increases by 1. The electron antineutrino (ν̄ₑ) is required to conserve energy, momentum, angular momentum, and lepton number."
            },
            {
                "question_id": "nuclear_004_partially_correct",
                "question_text": "Calculate the Q-value for the alpha decay of ²²⁶Ra → ²²²Rn + α. Given: Mass of ²²⁶Ra = 226.025403 u, Mass of ²²²Rn = 222.017570 u, Mass of α particle = 4.002603 u.",
                "student_answer": "Q-value is the energy released in the reaction. Q = (initial mass - final masses) × c². Q = (226.025403 - 222.017570 - 4.002603) × 931.5 MeV/u = 0.00523 × 931.5 = 4.87 MeV. This energy comes from the mass defect.",
                "reference_answer": "Q-value = (Mi - Mf)c² = (M(²²⁶Ra) - M(²²²Rn) - M(α))c² = (226.025403 - 222.017570 - 4.002603) × 931.5 MeV/u = 4.87 MeV"
            },
            {
                "question_id": "nuclear_005_conceptual_gap",
                "question_text": "Explain why nuclear fission releases energy while nuclear fusion also releases energy, even though they are opposite processes.",
                "student_answer": "Both fission and fusion release energy because they both break chemical bonds and form new ones. In fission, heavy atoms split apart releasing stored energy, and in fusion, light atoms combine and release energy when they stick together.",
                "reference_answer": "Both processes move nuclei toward greater binding energy per nucleon. Fission of heavy nuclei (A>56) and fusion of light nuclei (A<56) both increase binding energy per nucleon, releasing the difference as kinetic energy. This is due to the shape of the binding energy curve with maximum at Fe-56."
            },
            {
                "question_id": "nuclear_006_calculation_error",
                "question_text": "What is the nuclear radius of ²⁰⁸Pb using the formula R = r₀A¹/³, where r₀ = 1.2 fm?",
                "student_answer": "Using the formula R = r₀A¹/³, I get R = 1.2 × (208)¹/³. Let me calculate (208)¹/³ = 208^(1/3) ≈ 6.8. So R = 1.2 × 6.8 = 8.16 fm",
                "reference_answer": "Using R = r₀A¹/³ with r₀ = 1.2 fm and A = 208: R = 1.2 × (208)¹/³ = 1.2 × 5.925 = 7.11 fm"
            }
        ]
    
    def save_nuclear_questions(self, filename="nuclear_physics_test.json"):
        """Save nuclear physics questions to test file"""
        file_path = self.test_data_dir / "input" / filename
        questions_data = {"questions": self.nuclear_questions}
        
        with open(file_path, 'w') as f:
            json.dump(questions_data, f, indent=2)
        
        print(f"Nuclear physics questions saved to: {file_path}")
        return file_path
    
    def mock_student_responses(self):
        """Generate realistic student responses for interactive sessions"""
        response_scenarios = {
            "confused_about_decay": [
                "I'm not sure about the relationship between half-life and decay constant",
                "Oh, so λ = ln(2)/t₁/₂?",
                "I see, so I should use N = N₀(1/2)^n instead"
            ],
            "misconception_beta_decay": [
                "But if an electron leaves, shouldn't the charge decrease?",
                "Wait, does the electron come from a neutron changing?",
                "So a neutron becomes a proton plus an electron and neutrino?"
            ],
            "calculation_confusion": [
                "I think I made an arithmetic error",
                "Let me recalculate the cube root more carefully",
                "Oh I see, 208^(1/3) is about 5.9, not 6.8"
            ],
            "conceptual_understanding": [
                "I think I'm confusing nuclear and chemical processes",
                "Is this about binding energy per nucleon?",
                "So it's about moving toward iron-56 on the binding energy curve?"
            ],
            "general_confusion": [
                "I'm not quite following the concept",
                "Could you explain that differently?",
                "I think I need to review this topic more"
            ]
        }
        return response_scenarios
    
    def create_response_for_question(self, question_id):
        """Create appropriate mock responses based on question type"""
        scenarios = self.mock_student_responses()
        
        if "misconception" in question_id:
            return scenarios["misconception_beta_decay"]
        elif "needs_feedback" in question_id:
            return scenarios["confused_about_decay"]
        elif "calculation_error" in question_id:
            return scenarios["calculation_confusion"]
        elif "conceptual_gap" in question_id:
            return scenarios["conceptual_understanding"]
        else:
            return scenarios["general_confusion"]
    
    def mock_interactive_input(self, responses):
        """Mock input function that cycles through predefined responses"""
        response_iter = iter(responses)
        
        def mock_input(prompt=""):
            try:
                response = next(response_iter)
                print(f"[STUDENT RESPONSE] {response}")
                return response
            except StopIteration:
                print("[STUDENT RESPONSE] exit")
                return "exit"
        
        return mock_input
    
    async def test_nuclear_physics_session(self):
        """Run a complete session with nuclear physics questions"""
        test_name = "Nuclear Physics Session"
        
        # Save questions to file
        questions_file = self.save_nuclear_questions()
        
        # Load and validate questions
        questions = load_and_validate_questions(questions_file)
        
        if not questions:
            self.test_results.append((test_name, "FAIL", "Could not load questions"))
            return
        
        # Prepare mixed responses for different question types
        all_responses = []
        for question in questions:
            question_responses = self.create_response_for_question(question["question_id"])
            all_responses.extend(question_responses)
        
        # Add exit command at the end
        all_responses.append("exit")
        
        print(f"\n=== STARTING NUCLEAR PHYSICS TEST SESSION ===")
        print(f"Questions loaded: {len(questions)}")
        print(f"Mock responses prepared: {len(all_responses)}")
        
        # Run the session with mocked input
        with patch('builtins.input', self.mock_interactive_input(all_responses)):
            try:
                session_id = f"nuclear_physics_{datetime_uuid('test')}"
                await grade_ant_plus_main(
                    questions,
                    session_id=session_id,
                    user_id="nuclear_student"
                )
                self.test_results.append((test_name, "PASS", f"Processed {len(questions)} nuclear physics questions"))
            except Exception as e:
                self.test_results.append((test_name, "FAIL", str(e)))
    
    async def test_specific_nuclear_concepts(self):
        """Test specific nuclear physics concepts"""
        test_name = "Nuclear Concepts Validation"
        
        try:
            # Test just the conceptual questions
            conceptual_questions = [q for q in self.nuclear_questions if "conceptual" in q["question_id"]]
            
            if conceptual_questions:
                session_id = f"concepts_{datetime_uuid('test')}"
                with patch('builtins.input', self.mock_interactive_input(["I need help with this concept", "exit"])):
                    await grade_ant_plus_main(
                        conceptual_questions,
                        session_id=session_id,
                        user_id="concept_student"
                    )
                    self.test_results.append((test_name, "PASS", "Conceptual questions processed"))
            else:
                self.test_results.append((test_name, "SKIP", "No conceptual questions found"))
                
        except Exception as e:
            self.test_results.append((test_name, "FAIL", str(e)))
    
    async def test_calculation_problems(self):
        """Test calculation-heavy problems"""
        test_name = "Nuclear Calculations"
        
        try:
            # Test calculation questions
            calc_questions = [q for q in self.nuclear_questions if any(word in q["question_id"] 
                            for word in ["correct", "calculation", "partially"])]
            
            if calc_questions:
                session_id = f"calculations_{datetime_uuid('test')}"
                with patch('builtins.input', self.mock_interactive_input(["Let me check my math", "exit"])):
                    await grade_ant_plus_main(
                        calc_questions,
                        session_id=session_id,
                        user_id="calc_student"
                    )
                    self.test_results.append((test_name, "PASS", f"Processed {len(calc_questions)} calculation problems"))
            else:
                self.test_results.append((test_name, "SKIP", "No calculation questions found"))
                
        except Exception as e:
            self.test_results.append((test_name, "FAIL", str(e)))
    
    def generate_test_report(self):
        """Generate comprehensive test report"""
        print("\n" + "="*80)
        print("NUCLEAR PHYSICS TEST RESULTS")
        print("="*80)
        
        if not self.test_results:
            print("No test results available")
            return
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results if result[1] == "PASS")
        failed_tests = sum(1 for result in self.test_results if result[1] == "FAIL")
        skipped_tests = sum(1 for result in self.test_results if result[1] == "SKIP")
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Skipped: {skipped_tests}")
        if total_tests > 0:
            print(f"Success Rate: {(passed_tests/(total_tests-skipped_tests))*100:.1f}%")
        
        print("\nDETAILED RESULTS:")
        print("-" * 80)
        
        for test_name, status, details in self.test_results:
            status_icons = {"PASS": "✓", "FAIL": "✗", "SKIP": "○"}
            icon = status_icons.get(status, "?")
            print(f"{icon} {test_name:.<50} {status}")
            if details:
                print(f"   Details: {details}")
        
        print(f"\nTest data location: {self.test_data_dir}")
        print("Check the output directory for generated reports and audio files")
    
    async def run_all_nuclear_tests(self):
        """Run all nuclear physics tests"""
        print("Starting Nuclear Physics Test Suite for GradeAnt+")
        print("="*80)
        
        test_functions = [
            self.test_nuclear_physics_session,
            self.test_specific_nuclear_concepts,
            self.test_calculation_problems
        ]
        
        for test_func in test_functions:
            print(f"\nRunning {test_func.__name__}...")
            try:
                await test_func()
            except Exception as e:
                self.test_results.append((test_func.__name__, "FAIL", f"Test execution error: {str(e)}"))
        
        self.generate_test_report()

async def main():
    """Main test execution"""
    runner = NuclearPhysicsTestRunner()
    
    try:
        await runner.run_all_nuclear_tests()
        print("\nNuclear physics test suite completed!")
        print("Review the generated reports and audio summaries in the output directory.")
    except Exception as e:
        print(f"Test suite failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())