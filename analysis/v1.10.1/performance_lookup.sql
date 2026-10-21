WITH ranked AS (
 SELECT *,ROW_NUMBER() OVER(PARTITION BY model_key,condition ORDER BY end_to_end_ms,task_id,qid) AS rn,
 COUNT(*) OVER(PARTITION BY model_key,condition) AS n
 FROM main.question_runs WHERE stage='performance'), stats AS (
 SELECT model_key,model,condition,MAX(n) AS n_observations,COUNT(DISTINCT qid) AS unique_questions,
 AVG(CASE WHEN rn IN ((n+1)/2,(n+2)/2) THEN end_to_end_ms END) AS p50,
 CASE WHEN MAX(n)>=100 THEN
 SUM(CASE WHEN rn=CAST((n-1)*0.95 AS INTEGER)+1 THEN end_to_end_ms*(1-((n-1)*0.95-CAST((n-1)*0.95 AS INTEGER))) ELSE 0 END)+
 SUM(CASE WHEN rn=CAST((n-1)*0.95 AS INTEGER)+2 THEN end_to_end_ms*((n-1)*0.95-CAST((n-1)*0.95 AS INTEGER)) ELSE 0 END)
 ELSE NULL END AS p95
 FROM ranked GROUP BY model_key,model,condition)
SELECT *,printf('%.1f',p50) AS p50_text,CASE WHEN p95 IS NULL THEN '不报告（n=25）' ELSE printf('%.1f',p95) END AS p95_text
FROM stats ORDER BY model_key,condition;
