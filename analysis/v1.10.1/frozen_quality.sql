SELECT model_key, model, split, condition,
       COUNT(*) AS n,
       SUM(CASE WHEN parse_status = 'ok' AND parsed_choice = gold_choice THEN 1 ELSE 0 END) AS correct,
       1.0 * SUM(CASE WHEN parse_status = 'ok' AND parsed_choice = gold_choice THEN 1 ELSE 0 END) / COUNT(*) AS accuracy,
       SUM(format_failure) AS format_failures,
       1.0 * SUM(format_failure) / COUNT(*) AS format_rate,
       1.0 * SUM(CASE WHEN parse_status = 'ok' THEN 1 ELSE 0 END) / COUNT(*) AS valid_parse_rate
FROM main.question_runs
WHERE stage = 'quality' AND split = 'frozen_test' AND condition IN ('S0','S1','S2')
GROUP BY model_key, model, split, condition
ORDER BY MIN(model_order), condition;
