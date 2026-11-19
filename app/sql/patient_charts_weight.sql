SELECT '29463-7' AS LoincCode, 'Weight' AS ResultName, Trim([DATAVALUE]) AS ResultValue, OBSDATE AS ReportDate
FROM OBSERVATIONS a join PATIENTS b on a.Internalid = b.internalid
where a.INTERNALID = ? and datacode in (8) and a.RECORDSTATUS = 1
order by OBSDATE