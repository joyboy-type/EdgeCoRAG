SELECT model_key,model,MAX(allocated_bytes)/1073741824.0 AS peak_allocated_gib,
 MAX(reserved_bytes)/1073741824.0 AS peak_reserved_gib,
 printf('%.2f',MAX(allocated_bytes)/1073741824.0) AS allocated_text,
 printf('%.2f',MAX(reserved_bytes)/1073741824.0) AS reserved_text
FROM main.memory_observations GROUP BY model_key,model ORDER BY model_key;
