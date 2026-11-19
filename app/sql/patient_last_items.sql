SELECT CONVERT(varchar(8), Max(Services.serviceDate), 3) AS MaxOfServiceDate,  
LEFT(USERS.FIRSTNAME, 1) + LEFT(USERS.SURNAME, 1) AS UserInitials,  SERVICES.MBSItem, 
LEFT(Services.description, 20) AS Description
FROM Invoices INNER JOIN SERVICES ON INVOICES.InvoiceID = SERVICES.InvoiceID 
INNER JOIN PATIENTS ON Invoices.Internalid = PATIENTS.InternalId 
INNER JOIN USERS ON USERS.USERId = Invoices.USERId 
GROUP BY Invoices.UserId, Invoices.Internalid, PATIENTS.InternalId, 
SERVICES.MBSItem, SERVICES.RecordStatus, Services.description, USERS.FIRSTNAME, USERS.SURNAME 
HAVING PATIENTS.InternalId= ? AND SERVICES.RecordStatus < 10 
ORDER BY Max(Services.serviceDate) DESC;
