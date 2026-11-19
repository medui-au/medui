SELECT FORMAT(DATEADD(second, APPOINTMENTS.APPOINTMENTTIME, APPOINTMENTS.APPOINTMENTDATE), 'd/M/yy H:mm') + ' ' +  
       RTRIM(LEFT(USERS.FIRSTNAME, 1) + LEFT(USERS.SURNAME, 1)) + ' ' + CAST(DateDiff(dd, Appointments.Created, GetDate()) AS VARCHAR) + 'd ago' AS APPT_WHEN
FROM APPOINTMENTS 
INNER JOIN USERS ON APPOINTMENTS.USERID = USERS.USERID  
WHERE InternalId = ? AND Appointments.RECORDStatus = 1 AND DateDiff(dd, GetDate(), AppointmentDate) > -1 
ORDER BY AppointmentDate, AppointmentTime;
