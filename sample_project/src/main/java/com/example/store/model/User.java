package com.example.store.model;

import javax.persistence.Entity;
import javax.persistence.Id;
import javax.persistence.OneToMany;
import java.util.List;

@Entity
// PROBLEMA: sem @Table(indexes=...) para email ou status
// → aciona MISSING_INDEX via findByEmail / findByStatus no UserRepository
public class User {

    @Id
    private Long id;

    private String email;   // sem @Index → MISSING_INDEX
    private String status;  // sem @Index → MISSING_INDEX
    private String username;

    // PROBLEMA: @OneToMany sem FetchType.EAGER e sem @JsonManagedReference
    // → aciona LAZY_LOADING: serialização JSON pode causar LazyInitializationException
    @OneToMany
    private List<Order> orders;

    // getters/setters omitidos para brevidade
}
