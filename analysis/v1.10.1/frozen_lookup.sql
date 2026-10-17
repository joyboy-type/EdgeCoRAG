SELECT model_key, model, SUM(CASE WHEN condition='S0' THEN 1 ELSE 0 END) AS n,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S0' THEN correct ELSE 0 END)/SUM(condition='S0')) AS S0,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S1' THEN correct ELSE 0 END)/SUM(condition='S1')) AS S1,
       printf('%.2f%%',100.0*SUM(CASE WHEN condition='S2' THEN correct ELSE 0 END)/SUM(condition='S2')) AS S2
FROM main.question_runs
WHERE stage='quality' AND split='frozen_test' AND condition IN ('S0','S1','S2')
GROUP BY model_key, model ORDER BY MIN(model_order);
