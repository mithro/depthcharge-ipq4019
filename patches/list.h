/*
 * Copyright 2012 Google Inc.
 *
 * See file CREDITS for list of people who contributed to this
 * project.
 *
 * This program is free software; you can redistribute it and/or
 * modify it under the terms of the GNU General Public License as
 * published by the Free Software Foundation; either version 2 of
 * the License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but without any warranty; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 */

#ifndef __BASE_LIST_H__
#define __BASE_LIST_H__

#include <stddef.h>
#include <stdint.h>

#include "base/container_of.h"

typedef struct ListNode {
	struct ListNode *next;
	struct ListNode *prev;
} ListNode;

// Remove ListNode node from the doubly linked list it's a part of.
void list_remove(ListNode *node);
// Insert ListNode node after ListNode after in a doubly linked list.
void list_insert_after(ListNode *node, ListNode *after);
// Insert ListNode node before ListNode before in a doubly linked list.
void list_insert_before(ListNode *node, ListNode *before);

/*
 * Iterate a NULL-terminated linear list. The termination check needs to
 * compare the raw ListNode pointer (head.next ... NULL) rather than the
 * container-of'd address &(ptr->member), because modern GCC treats
 * &(ptr->member) as "always non-NULL" under -O2 (deref of NULL is UB),
 * which strips the loop's terminator and walks one past the end.
 * The trick: stash the raw next pointer in a hidden variable on each
 * step so the compiler can't optimise away the NULL test.
 */
#define list_for_each(ptr, head, member)                                \
	for (ListNode *_lfe_n = (head).next;                            \
	     _lfe_n && ((ptr) = container_of(_lfe_n, typeof(*(ptr)),    \
					     member), 1);               \
	     _lfe_n = (ptr)->member.next)

#endif /* __BASE_LIST_H__ */
