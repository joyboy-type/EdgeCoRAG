SELECT model_key,category,qid FROM review_candidates
 WHERE model_key=:model_key AND category=:category
 AND qid NOT IN (SELECT value FROM json_each(:excluded_qids))
 ORDER BY selection_hash LIMIT 1;
