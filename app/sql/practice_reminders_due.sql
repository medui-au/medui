SELECT TOP (1000)
       R.[REMINDERID]
      -- Patient Details
      ,TRIM(P.Firstname) + ' ' + TRIM(P.Surname) AS Patient_Name
      ,TRIM(ISNULL(P.MOBILEPHONE, '')) +
       CASE WHEN P.MOBILEPHONE IS NOT NULL AND P.HOMEPHONE IS NOT NULL THEN ' / ' ELSE '' END +
       TRIM(ISNULL(P.HOMEPHONE, '')) AS Patient_Phone
      -- Next Appointment
      ,NextAppt.next_appt
      ,R.[INTERNALID]
      ,TRIM(R.[REASONTEXT]) + ' ' + ISNULL(R.COMMENTS, '') AS REASONTEXT
      ,CAST(R.[REMINDERDUE] AS DATE) AS [REMINDERDUE]
      ,CASE
            WHEN R.[UPDATED] >= R.[CREATED] THEN CAST(R.[UPDATED] AS DATE)
            ELSE CAST(R.[CREATED] AS DATE)
       END AS [LAST_ACTION_DATE]
      ,CASE
            WHEN R.[UPDATED] >= R.[CREATED] THEN TRIM(UU.FirstName) + ' ' + TRIM(UU.Surname)
            ELSE TRIM(UC.FirstName) + ' ' + TRIM(UC.Surname)
       END AS [LAST_ACTION_BY_NAME]
      ,TRIM(U.FirstName) + ' ' + TRIM(U.Surname) AS UserName
  FROM [BPSPATIENTS].[dbo].[REMINDERS] R
  LEFT JOIN [BPSPATIENTS].[dbo].[patients] P  ON R.INTERNALID = P.INTERNALID
  LEFT JOIN [BPSPATIENTS].[dbo].[users]    U  ON R.UserId     = U.UserId
  LEFT JOIN [BPSPATIENTS].[dbo].[users]    UC ON R.CreatedBy  = UC.UserId
  LEFT JOIN [BPSPATIENTS].[dbo].[users]    UU ON R.UpdatedBy  = UU.UserId
  OUTER APPLY (
      SELECT TOP (1)
          FORMAT(app.APPOINTMENTDATE, 'd/MM/yy') + ' ' +
          LEFT(TRIM(ISNULL(us.FIRSTNAME, '')), 1) +
          LEFT(TRIM(ISNULL(us.SURNAME, '')), 1) AS next_appt
        FROM [BPSPATIENTS].[dbo].[APPOINTMENTS] app
        JOIN [BPSPATIENTS].[dbo].[USERS] us ON app.USERID = us.USERID
       WHERE app.INTERNALID   = R.INTERNALID
         AND app.APPOINTMENTDATE >= CAST(GETDATE() AS DATE)
         AND app.RECORDSTATUS = 1
       ORDER BY app.APPOINTMENTDATE ASC
  ) AS NextAppt
 WHERE R.RECORDSTATUS <> 0
   AND R.REMINDERSTATUS = 1
   AND DATEDIFF(MM, GETDATE(), R.REMINDERDUE) IN (0, 1)
   AND R.REASONTEXT NOT LIKE 'Health Assessment%'
 ORDER BY R.REMINDERDUE DESC
