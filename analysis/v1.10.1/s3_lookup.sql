WITH subset AS (
 SELECT s.model_key,s.model,s.split,COUNT(*) AS paired_n,
 (SELECT COUNT(*) FROM main.question_runs p WHERE p.model_key=s.model_key AND p.split=s.split AND p.stage='quality' AND p.condition='S1') AS parent_n,
 AVG(r.correct) AS s1_subset_accuracy,AVG(s.correct) AS s3_subset_accuracy
 FROM main.question_runs s JOIN main.question_runs r
 ON r.model_key=s.model_key AND r.split=s.split AND r.qid=s.qid AND r.stage='quality' AND r.condition='S1'
 WHERE s.stage='quality' AND s.condition='S3-pure'
 GROUP BY s.model_key,s.model,s.split)
SELECT *,printf('%.2f%%',100.0*paired_n/parent_n) AS coverage_text,
 printf('%.2f%%',100*s1_subset_accuracy) AS s1_text,printf('%.2f%%',100*s3_subset_accuracy) AS s3_text,
 printf('%+.2f',100*(s3_subset_accuracy-s1_subset_accuracy)) AS delta
FROM subset ORDER BY model_key,split;
