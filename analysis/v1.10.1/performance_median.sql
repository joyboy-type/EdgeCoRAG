WITH ranked AS (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY model_key, condition ORDER BY end_to_end_ms, task_id, qid) AS rn,
            COUNT(*) OVER (PARTITION BY model_key, condition) AS n
  FROM main.question_runs
  WHERE stage = 'performance' AND condition IN ('S0','S1','S2')
)
SELECT model_key, model, condition, MAX(n) AS n_observations,
       COUNT(DISTINCT qid) AS unique_questions, COUNT(DISTINCT repeat_index) AS repeats,
       AVG(CASE WHEN rn IN ((n + 1) / 2, (n + 2) / 2) THEN end_to_end_ms END) AS end_to_end_p50_ms,
       SUM(format_failure) AS format_failures, AVG(generated_tokens) AS mean_generated_tokens,
       MAX(hardware_id) AS hardware_id
FROM ranked
GROUP BY model_key, model, condition
ORDER BY MIN(model_order), condition;
