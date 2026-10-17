SELECT split,model_key,pattern,COUNT(*) AS n FROM triples
 GROUP BY split,model_key,pattern ORDER BY split,model_key,pattern;
