// Package main — a small self-contained Go utility.
//
// StringSet implements a set of strings backed by a map, with the
// usual Add / Contains / Remove / Len / List operations.
package main

import "sort"

// StringSet is a collection of unique strings.
type StringSet struct {
	items map[string]struct{}
}

// NewStringSet returns an empty StringSet.
func NewStringSet() *StringSet {
	return &StringSet{items: make(map[string]struct{})}
}

// Add inserts a string into the set. Returns true if newly added.
func (s *StringSet) Add(v string) bool {
	if _, ok := s.items[v]; ok {
		return false
	}
	s.items[v] = struct{}{}
	return true
}

// Contains reports whether v is in the set.
func (s *StringSet) Contains(v string) bool {
	_, ok := s.items[v]
	return ok
}

// Remove deletes v from the set. Returns true if v was present.
func (s *StringSet) Remove(v string) bool {
	if _, ok := s.items[v]; !ok {
		return false
	}
	delete(s.items, v)
	return true
}

// Len returns the number of items in the set.
func (s *StringSet) Len() int {
	return len(s.items)
}

// List returns a sorted slice of all items in the set.
func (s *StringSet) List() []string {
	out := make([]string, 0, len(s.items))
	for v := range s.items {
		out = append(out, v)
	}
	sort.Strings(out)
	return out
}

func main() {}
