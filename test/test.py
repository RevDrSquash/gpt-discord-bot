import deepeval
from deepeval.metrics import GEval
from deepeval.test_case import LLMTestCase
from deepeval.test_case import LLMTestCaseParams
from deepeval.dataset import EvaluationDataset

import pathlib
from pathlib import Path

import src.constants

correctness_metric = GEval(
    name="Correctness",
    model="gpt-4o",
    evaluation_params=[
        LLMTestCaseParams.CONTEXT,
        LLMTestCaseParams.ACTUAL_OUTPUT],
    evaluation_steps=[
       'Compare the actual output directly with the expected output to verify factual accuracy.',
       'Check if all elements mentioned in the expected output are present and correctly represented in the actual output.',
       'Assess if there are any discrepancies in details, values, or information between the actual and expected outputs.'
    ],
)

actual_output_first="""
To summarize, here’s how to conduct a decisive attack:
Declare Your Target: Announce who or what you are attacking.
Choose Your Action: Specify that you are making a decisive attack.
Roll Your Dice Pool: Combine your relevant Attribute (like Dexterity or Strength) and your Ability (like Martial Arts or Melee) to form your dice pool. Add any bonuses from charms or situational advantages.
Determine Successes: Roll the dice and count the number of successes (usually a success is a result of 7 or higher on a single d10).
Compare to Target's Defense: The successes must exceed your target’s defense to hit.
Calculate Damage: Use the weapon's damage value and add it to the number of successes you rolled. Damage typically is done in lethal or bashing, depending on the weapon.
Apply Wounds: Subtract the total damage from your target's health levels.
If you need more intricate details on any specific step, please let me know, or specify any relevant aspects of your character or situation.
"""

first_test_case = LLMTestCase(input="How do I make a decisive attack?",
                              actual_output=actual_output_first,
                              context=[Path('test/resolving a decisive attack.txt').read_text(encoding="utf8")])


actual_output_second="""
To make a withering attack in Exalted 3rd Edition, follow these steps:
Choose Your Combat Ability: Decide what combat Ability your character will use for the attack (Melee, Archery, Brawl, Martial Arts, or Thrown).
Roll to Hit: Roll your dice pool, which consists of:
Dexterity + Relevant Combat Ability + Weapon's Accuracy (if applicable) + any other modifiers.
The target's Defense is the difficulty of this roll. If your total successes are fewer than the target's Defense, the attack fails.
Determine Raw Damage:
If the attack succeeds, calculate your raw damage as follows:
Raw damage = (Strength + Weapon Damage + Successes on the attack roll).
Note: Some weapons, like firewands or crossbows, may omit Strength from this calculation.
Apply Soak: Subtract the target's soak from your raw damage. The resulting damage cannot drop below the weapon's Overwhelming rating.
Roll Damage: Roll a dice pool equal to the damage that remains after soak. Remember, in withering attacks, the Double 10s rule applies, so you might get extra successes.
Adjust Initiative:
After resolving the damage, you gain one point of Initiative for landing a successful withering attack.
Subtract the total successes from the damage roll from the target's Initiative, and add that amount to your character's Initiative.
By following these steps, you will effectively perform a withering attack, damaging your opponent's Initiative and gaining an advantage in combat.
"""
second_test_case = LLMTestCase(input="How do I make a withering attack?",
                              actual_output=actual_output_second,
                              context=[Path('test/resolving a withering attack.txt').read_text(encoding="utf8")])

test_cases = [first_test_case, second_test_case]

dataset = EvaluationDataset(test_cases=test_cases)

evaluation_output = dataset.evaluate([correctness_metric])

print(evaluation_output)
