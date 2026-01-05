# CUQ Test - Assistant Project (Ulster University Standard)

## Source
- Official CUQ page: https://www.ulster.ac.uk/research/topic/computer-science/artificial-intelligence/projects/cuq
- Questionnaire PDF: https://www.ulster.ac.uk/__data/assets/pdf_file/0009/478809/Chatbot-Usability-Questionnaire.pdf
- Calculation tool (Excel): https://www.ulster.ac.uk/__data/assets/excel_doc/0010/478810/CUQ-Calculation-Tool.xlsx

## Overview
The CUQ is a questionnaire designed to measure chatbot usability. It is comparable to the
System Usability Scale (SUS) and may be used alongside SUS or other usability metrics.

## When and How to Use
- Use during the post-test evaluation phase of chatbot usability tests.
- Administer on paper or electronically (e.g., a web survey tool).

## Scale
All items use a five-point Likert scale:
1 = Strongly Disagree, 2 = Disagree, 3 = Neutral, 4 = Agree, 5 = Strongly Agree.
Odd-numbered items are positive; even-numbered items are negative.

## Questionnaire (Original CUQ Items)
1. The chatbot's personality was realistic and engaging
2. The chatbot seemed too robotic
3. The chatbot was welcoming during initial setup
4. The chatbot seemed very unfriendly
5. The chatbot explained its scope and purpose well
6. The chatbot gave no indication as to its purpose
7. The chatbot was easy to navigate
8. It would be easy to get confused when using the chatbot
9. The chatbot understood me well
10. The chatbot failed to recognise a lot of my inputs
11. Chatbot responses were useful, appropriate and informative
12. Chatbot responses were irrelevant
13. The chatbot coped well with any errors or mistakes
14. The chatbot seemed unable to handle any errors
15. The chatbot was very easy to use
16. The chatbot was very complex

## Scoring (CUQ Usage Guide)
1. Assign each item a score from 1 to 5.
2. Sum all odd-numbered items.
3. Sum all even-numbered items.
4. Subtract 8 from the odd-numbered sum.
5. Subtract the even-numbered sum from 40.
6. Add the results of steps 4 and 5 (score out of 64).
7. Convert to a 0-100 score: (score / 64) * 100.

## Project Task Script (Optional; not part of CUQ)
1. Register and log in.
2. Start a new session and ask a domain question.
3. Inspect citations for a response.
4. Provide feedback on an answer.
5. Search previous conversations and export history.
6. Upload a file and trigger ingestion.
7. Ask a follow-up question using the ingested content.
8. (Optional admin) Verify a source and check index health.

## Project-Specific Addendum (Optional; not part of CUQ)
A. Citations are clear and easy to inspect.
B. File upload and ingestion are reliable.
C. Session management (rename, pin, archive, export) is easy to use.
D. Feedback and escalation workflows are clear.
E. The system communicates when it is searching or streaming.
F. Admin settings for sources and retrieval are easy to manage.

## Validation Notes (From Ulster University CUQ Page)
- Validated in August 2019 as part of a PhD at Ulster University.
- 26 participants evaluated three chatbots (good, average, poor quality).
- Limitations: small sample size and limited chatbot types.

## Citation
Samuel Holmes, Anne Moorhead, Raymond Bond, Huiru Zheng, Vivien Coates, and Michael Mctear. 2019.
Usability testing of a healthcare chatbot: Can we use conventional methods to assess conversational user interfaces?
In Proceedings of the 31st European Conference on Cognitive Ergonomics (ECCE 2019), ACM, New York, NY, USA, 207-214.
https://doi.org/10.1145/3335082.3335094
