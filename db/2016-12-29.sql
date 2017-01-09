ALTER TABLE  `users` ADD  `first_name` VARCHAR( 40 ) NULL AFTER  `id` ,
ADD  `last_name` VARCHAR( 40 ) NULL AFTER  `first_name` ,
ADD  `nick_name` VARCHAR( 40 ) NULL AFTER  `last_name` ;