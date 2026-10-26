"""
The scam check, inside the app (26 Oct 2026: replaces the n8n workflow in n8n/).

    rules.py    stage 0: where the apply link leads, contact details in the post (no AI)
    vectors.py  stage 1: post sentences vs the bank of known scam / honest phrases (embeddings)
    judge.py    stage 2: the AI judge (gpt-4o on Azure), 5 posts per call, must quote the post
    fuse.py     quotes checked against the post, the three stages combined into one verdict
    runner.py   takes waiting posts from the list, runs the stages, saves the verdicts
    agent.py    a second look at "needs a look" posts: an agent checks the company and the link

Same logic and thresholds as the n8n Code nodes (tests/test_pipeline.py runs both on the same
posts and compares), so verdicts don't change with the move; it just runs without n8n.
"""
from moderation.pipeline.runner import check_waiting, start_worker, wake  # noqa: F401
