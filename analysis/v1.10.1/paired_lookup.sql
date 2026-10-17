WITH contrasts(left_condition,right_condition,comparison) AS
 (VALUES ('S0','S1','S1 − S0'),('S1','S2','S2 − S1'))
SELECT l.model_key,l.model,c.comparison,COUNT(*) AS n,
       100.0*AVG(r.correct-l.correct) AS delta_pp,
       printf('%+.2f',100.0*AVG(r.correct-l.correct)) AS delta,
       printf('[%+.2f, %+.2f]',b.ci_low_pp,b.ci_high_pp) AS interval,
       b.ci_low_pp,b.ci_high_pp,
       SUM(l.correct=0 AND r.correct=1) AS improvements,
       SUM(l.correct=1 AND r.correct=0) AS regressions
FROM contrasts c
JOIN main.question_runs l ON l.condition=c.left_condition AND l.stage='quality' AND l.split='frozen_test'
JOIN main.question_runs r ON r.model_key=l.model_key AND r.split=l.split AND r.qid=l.qid
 AND r.stage=l.stage AND r.condition=c.right_condition
JOIN main.bootstrap_intervals b ON b.model_key=l.model_key AND b.split=l.split AND b.comparison=c.comparison
GROUP BY l.model_key,l.model,c.comparison ORDER BY MIN(l.model_order),c.comparison;
