
ALTER TABLE  `users` CHANGE  `location`  `lat` VARCHAR( 20 ) CHARACTER SET latin1 COLLATE latin1_swedish_ci NULL ;
ALTER TABLE  `users` ADD  `lon` VARCHAR( 20 ) NULL AFTER  `lat` ;
